"""
高考助手核心服务 - 完整版（从 saibo.py 迁移）
"""
import os
import shutil
import json
import csv
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import threading

import dashscope
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from django.conf import settings


# ==================== 配置 ====================
PROVINCE_CODE = {
    "北京": 11, "天津": 12, "河北": 13, "山西": 14, "内蒙古": 15,
    "辽宁": 21, "吉林": 22, "黑龙江": 23, "上海": 31, "江苏": 32,
    "浙江": 33, "安徽": 34, "福建": 35, "江西": 36, "山东": 37,
    "河南": 41, "湖北": 42, "湖南": 43, "广东": 44, "广西": 45,
    "海南": 46, "重庆": 50, "四川": 51, "贵州": 52, "云南": 53,
    "西藏": 54, "陕西": 61, "甘肃": 62, "青海": 63, "宁夏": 64, "新疆": 65
}

# GPU 配置
USE_GPU = True  # 是否使用 GPU


def get_device():
    """获取可用的设备"""
    if not USE_GPU:
        return "cpu"

    try:
        import torch
        if torch.cuda.is_available():
            print(f"✅ 检测到 GPU: {torch.cuda.get_device_name(0)}")
            print(f"   显存总量: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            return "cuda"
        else:
            print("⚠️ 未检测到 CUDA 可用 GPU，使用 CPU")
            return "cpu"
    except ImportError:
        print("⚠️ PyTorch 未安装，使用 CPU")
        return "cpu"
    except Exception as e:
        print(f"⚠️ GPU 检测失败: {e}，使用 CPU")
        return "cpu"


# ==================== 知识库 Skills ====================
vectorstore = None
vectorstore_lock = threading.Lock()
embeddings_instance = None


def get_embeddings():
    """获取 embedding 模型实例（单例，支持 GPU）"""
    global embeddings_instance

    if embeddings_instance is not None:
        return embeddings_instance

    device = get_device()
    print(f"正在加载 Embedding 模型 (BAAI/bge-large-zh-v1.5, device={device})...")

    try:
        # 配置模型参数 - 正确的参数格式
        model_kwargs = {}

        # 根据设备设置
        if device == "cuda":
            model_kwargs = {'device': 'cuda'}
        else:
            model_kwargs = {'device': 'cpu'}

        # 编码参数 - 只包含 SentenceTransformer.encode 支持的参数
        # 支持的参数: normalize_embeddings, batch_size, show_progress_bar, convert_to_numpy 等
        encode_kwargs = {
            'normalize_embeddings': True,  # 归一化，提高检索质量
            'batch_size': 64 if device == "cuda" else 32,  # GPU 用更大批次
        }

        # 初始化 embeddings
        embeddings_instance = HuggingFaceEmbeddings(
            model_name="BAAI/bge-large-zh-v1.5",
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs
        )

        # 测试一下是否正常工作
        test_result = embeddings_instance.embed_query("测试")
        print(f"✅ Embedding 模型加载成功")
        print(f"   向量维度: {len(test_result)}")
        if device == "cuda":
            import torch
            print(f"   GPU 显存使用: {torch.cuda.memory_allocated() / 1024**2:.1f} MB")

        return embeddings_instance

    except Exception as e:
        print(f"❌ Embedding 模型加载失败: {e}")

        # 如果 GPU 加载失败，尝试回退到 CPU
        if device == "cuda":
            print("尝试回退到 CPU 模式...")
            try:
                model_kwargs = {'device': 'cpu'}
                encode_kwargs = {
                    'normalize_embeddings': True,
                    'batch_size': 32
                }
                embeddings_instance = HuggingFaceEmbeddings(
                    model_name="BAAI/bge-large-zh-v1.5",
                    model_kwargs=model_kwargs,
                    encode_kwargs=encode_kwargs
                )
                print("✅ 使用 CPU 模式加载成功")
                return embeddings_instance
            except Exception as e2:
                print(f"❌ CPU 模式也加载失败: {e2}")
                # 尝试最简单的配置
                try:
                    print("尝试使用默认配置...")
                    embeddings_instance = HuggingFaceEmbeddings(
                        model_name="BAAI/bge-large-zh-v1.5"
                    )
                    print("✅ 使用默认配置加载成功")
                    return embeddings_instance
                except Exception as e3:
                    print(f"❌ 所有尝试均失败: {e3}")
                    raise e

        raise e


def init_vectorstore():
    """初始化向量数据库 - 支持 GPU"""
    global vectorstore

    with vectorstore_lock:
        if vectorstore is not None:
            return vectorstore

        base_dir = Path(__file__).resolve().parent.parent
        references_dir = base_dir / "references" / "research"
        vector_db_path = base_dir / "zhang_faiss_index"

        # 获取 embedding 模型
        try:
            embeddings = get_embeddings()
        except Exception as e:
            print(f"❌ 获取 Embedding 模型失败: {e}")
            return None

        # 尝试加载已有向量库
        if vector_db_path.exists():
            try:
                print(f"尝试加载已有向量库: {vector_db_path}")

                # 检查向量库文件完整性
                index_file = vector_db_path / "index.faiss"
                pkl_file = vector_db_path / "index.pkl"

                if not index_file.exists() or not pkl_file.exists():
                    print("向量库文件不完整，将重新创建")
                    shutil.rmtree(vector_db_path)
                else:
                    # 使用 allow_dangerous_deserialization=True 加载本地创建的向量库
                    vectorstore = FAISS.load_local(
                        str(vector_db_path),
                        embeddings,
                        allow_dangerous_deserialization=True
                    )
                    print("✅ 向量库加载成功")
                    return vectorstore

            except Exception as e:
                print(f"⚠️ 向量库加载失败: {e}")
                print("将删除损坏的向量库并重新创建...")
                try:
                    shutil.rmtree(vector_db_path)
                    print("已删除损坏的向量库")
                except Exception as del_e:
                    print(f"删除失败: {del_e}")

        # 检查 references 目录
        if not references_dir.exists():
            print(f"⚠️ 目录不存在：{references_dir}")
            print("将创建目录，请手动添加参考文档")
            try:
                references_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"创建目录失败: {e}")
            return None

        # 加载文档
        print("加载文档...")
        documents = []
        md_files = list(references_dir.glob("*.md"))

        if not md_files:
            print(f"⚠️ 未找到任何 .md 文件，目录: {references_dir}")
            return None

        for md_file in md_files:
            print(f"   加载：{md_file.name}")
            try:
                loader = TextLoader(str(md_file), encoding='utf-8')
                docs = loader.load()
                for doc in docs:
                    doc.metadata["source"] = md_file.name
                documents.extend(docs)
            except Exception as e:
                print(f"   加载失败 {md_file.name}: {e}")
                continue

        if not documents:
            print("⚠️ 没有成功加载任何文档")
            return None

        print(f"共加载 {len(documents)} 个文档")

        # 分割文档
        print("分割文档...")
        try:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
            )
            chunks = text_splitter.split_documents(documents)
            print(f"分割为 {len(chunks)} 个文本块")
        except Exception as e:
            print(f"文档分割失败: {e}")
            return None

        # 创建向量库
        print("创建向量库...")
        if get_device() == "cuda":
            print("使用 GPU 加速创建向量库（可能需要几分钟）...")
        else:
            print("使用 CPU 创建向量库（可能需要几分钟）...")

        try:
            # 使用 embedding 模型创建向量库
            vectorstore = FAISS.from_documents(chunks, embeddings)
            print("✅ 向量库创建成功")

            # 保存向量库
            print(f"保存向量库到: {vector_db_path}")
            vectorstore.save_local(str(vector_db_path))
            print("✅ 向量库保存成功")
            return vectorstore

        except Exception as e:
            print(f"❌ 向量库创建失败: {e}")
            import traceback
            traceback.print_exc()
            return None


def search_skills(question: str) -> str:
    """搜索张雪峰知识库（Skills）"""
    global vectorstore

    if vectorstore is None:
        vectorstore = init_vectorstore()

    if vectorstore is None:
        return "知识库未就绪，请检查 references/research 目录下是否有 .md 文件"

    try:
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": 3}
        )
        docs = retriever.invoke(question)

        if not docs:
            return "未找到相关观点"

        result = ""
        for doc in docs:
            source = doc.metadata.get('source', '未知')
            content = doc.page_content.strip()
            if content:
                result += f"\n【{source}】\n{content}\n"

        return result.strip() if result.strip() else "未找到相关观点"

    except Exception as e:
        print(f"搜索知识库失败: {e}")
        return f"知识库搜索失败: {str(e)}"


# ==================== 数据查询 Tools ====================
def search_university_tool(school_name: str) -> str:
    """搜索大学基本信息"""
    url = "https://api.zjzw.cn/web/api/"
    payload = {
        "uri": "apidata/api/gkv3/school/lists",
        "keyword": school_name,
        "request_type": 1,
        "page": 1,
        "size": 10
    }
    headers = {"User-Agent": "Mozilla/5.0", "Connection": "close"}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=8)
        if resp.status_code != 200:
            return f"查询失败: HTTP {resp.status_code}"

        data = resp.json()
        schools = data.get('data', {}).get('item', [])
        if not schools:
            return f"未找到: {school_name}"

        results = []
        for school in schools[:5]:
            name = school.get('name')
            province = school.get('province_name')
            city = school.get('city_name')
            type_name = school.get('type_name')
            nature = school.get('nature_name')
            level_name = school.get('level_name')

            tags = []
            if school.get('f985') == 1:
                tags.append("985")
            if school.get('f211') == 1:
                tags.append("211")
            if school.get('dual_class') == '1':
                tags.append("双一流")

            tags_str = "、".join(tags) if tags else ("普通本科" if level_name == "本科" else level_name)
            results.append(f"{name} - {province}{city} | {type_name} | {nature} | {tags_str}")

        return "\n".join(results)
    except requests.Timeout:
        return f"查询超时，请稍后重试（{school_name}）"
    except Exception as e:
        return f"查询失败: {e}"


def get_admission_score(school_name: str = '成都东软学院', province: str = "四川", year: int = 2025) -> str:
    """
    智能查询分数线：自动使用最近有数据的年份
    """
    if year is None:
        year = 2025

    if year == 2026:
        year = 2025

    try:
        year = int(year)
    except:
        year = 2025

    if year > 2025:
        year = 2025
    if year < 2020:
        year = 2020

    def _fetch(year_to_fetch):
        url = "https://api.zjzw.cn/web/api/"
        payload = {
            "uri": "apidata/api/gkv3/school/lists",
            "keyword": school_name,
            "request_type": 1,
            "page": 1,
            "size": 5
        }
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None, f"搜索学校失败"

            schools = resp.json().get('data', {}).get('item', [])
            if not schools:
                return None, f"未找到大学: {school_name}"

            school_id = schools[0].get('school_id')
            school_full_name = schools[0].get('name')
            prov_code = PROVINCE_CODE.get(province)
            if not prov_code:
                return None, f"不支持的省份: {province}"

            score_url = f"https://static-data.gaokao.cn/www/2.0/schoolspecialscore/{school_id}/{year_to_fetch}/{prov_code}.json"
            score_resp = requests.get(score_url, headers=headers, timeout=10)

            if score_resp.status_code != 200:
                return None, None

            data = score_resp.json()
            scores = []
            for _, major_info in data.get('data', {}).items():
                for item in major_info.get('item', [])[:5]:
                    min_score = item.get('min')
                    if min_score:
                        scores.append(f"{item.get('sp_name')}: {min_score}分")

            if scores:
                return school_full_name, "\n".join(scores)
            return None, None
        except Exception as e:
            return None, f"查询失败: {e}"

    priority_years = [year, 2025, 2024, 2023, 2022]
    seen = set()
    priority_years = [y for y in priority_years if not (y in seen or seen.add(y))]

    for try_year in priority_years:
        if try_year < 2020:
            continue
        school_name_result, result = _fetch(try_year)
        if result and "未找到" not in result and "失败" not in result:
            if try_year != year:
                return f"📌 {year}年数据暂未公布，以下是{try_year}年参考数据：\n{school_name_result} {try_year}年{province}录取分数线:\n{result}\n\n（注：实际录取线每年会有波动，请结合位次综合判断）"
            else:
                return f"{school_name_result} {try_year}年{province}录取分数线:\n{result}"

    return f"未找到{school_name}在{province}近几年的录取数据"


def get_rank_tool(school_name: str = None) -> str:
    """查询软科排名"""
    base_dir = Path(__file__).resolve().parent.parent
    cache_file = base_dir / "shanghairanking_2026.csv"

    if not cache_file.exists():
        return "排名数据尚未缓存，请先运行一次爬取生成 shanghairanking_2026.csv 文件"

    rank_dict = {}
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 2:
                    rank_dict[row[1]] = int(row[0])
    except Exception as e:
        return f"读取排名文件失败: {e}"

    if not rank_dict:
        return "缓存文件为空"

    sorted_ranks = sorted(rank_dict.items(), key=lambda x: x[1])

    if school_name and school_name.strip():
        for name, rank in sorted_ranks:
            if school_name in name or name in school_name:
                return f"{name} 在2026软科排名中位列第{rank}名"
        return f"未找到: {school_name}，共获取 {len(sorted_ranks)} 所学校"

    result = "2026软科中国大学排名（前30名）:\n"
    for name, rank in sorted_ranks[:30]:
        result += f"{rank}. {name}\n"
    result += f"\n共获取 {len(sorted_ranks)} 所大学排名数据"
    return result


def get_current_time() -> str:
    return datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")


# ==================== 工具定义 ====================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前时间",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "搜索张雪峰知识库，获取张雪峰对高考志愿填报的观点、建议、经典语录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要搜索的问题，例如'四川460分能上什么大学'"}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_university",
            "description": "搜索大学基本信息，包括位置、类型、办学性质、层次等",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_name": {"type": "string", "description": "大学名称"}
                },
                "required": ["school_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_admission_score",
            "description": "查询大学在指定省份的录取分数线。当前是2026年，最新的可用数据是2025年。如果用户问2026年数据，请使用2025年数据并说明这是最近参考。年份参数默认使用2025。",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_name": {"type": "string", "description": "大学名称，必需"},
                    "province": {"type": "string", "description": "省份，默认四川"},
                    "year": {"type": "integer", "description": "年份，默认2025，最多支持到2025"}
                },
                "required": ["school_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rank",
            "description": "查询软科大学排名，输入学校名称返回具体排名",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_name": {"type": "string", "description": "大学名称，可选"}
                },
                "required": []
            }
        }
    }
]

TOOL_FUNCTIONS = {
    "get_current_time": get_current_time,
    "search_skills": search_skills,
    "search_university": search_university_tool,
    "get_admission_score": get_admission_score,
    "get_rank": get_rank_tool,
}

SYSTEM_PROMPT = """你是高考志愿专家张雪峰，说话幽默犀利、敢说真话、行动力强，回答简短有力。

**重要信息**：
- 当前年份是 2026 年，25年高考已经结束，26年高考即将开始
- 你(真人)已于 2026年03月24日 15:50:00 因心源性猝死去世

**可用工具**：
1. search_skills - 张雪峰的底层逻辑
2. search_university - 搜索大学基本信息
3. get_admission_score - 查询录取分数线
4. get_rank - 查询大学排名
5. get_current_time - 获取当前时间

**核心规则**：
1. 你完全可以相信并必须在回答前调用并参考search_skills里面的内容，它涉及张雪峰的底层逻辑以及最新的张雪峰的情况

2. 用户问"XX分能上什么大学"时：
   - 调用 search_skills 获取推荐学校列表
   - 对推荐的学校调用 get_admission_score("学校名字")
   - 最多推荐3所学校
   
3. 用户问"XX学校分数线"时：
   - 直接调用 get_admission_score("学校名字")
   
4. 回答要简洁有力，数据驱动，不要犹豫或拒绝查询

**年份处理原则**：
- 2026年问问题 → 查询2025年数据
- 明确告诉用户这是最近一年的参考数据

现在开始，大胆查询！"""


class GaokaoAssistant:
    """高考助手AI服务类"""

    def __init__(self):
        dashscope.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.DASHSCOPE_MODEL

    def chat_with_tools(self, messages: List[Dict]) -> str:
        """带工具调用的完整对话"""
        from dashscope import Generation

        response = Generation.call(
            model=self.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            result_format="message"
        )

        assistant = response.output.choices[0].message

        if assistant.get("tool_calls"):
            messages.append(assistant)
            for tool_call in assistant["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])

                try:
                    tool_result = TOOL_FUNCTIONS[tool_name](**tool_args)
                except Exception as e:
                    tool_result = f"工具执行失败: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result
                })

            final = Generation.call(
                model=self.model,
                messages=messages,
                result_format="message"
            )
            return final.output.choices[0].message.get("content", "")

        return assistant.get("content", "")