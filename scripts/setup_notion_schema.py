import os
import sys
import requests
from dotenv import load_dotenv


load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_VERSION = "2022-06-28"


def fail(message: str):
    print(f"[ERROR] {message}")
    sys.exit(1)


def notion_headers():
    if not NOTION_API_KEY:
        fail("缺少 NOTION_API_KEY，请检查 .env")

    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def get_database():
    if not NOTION_DATABASE_ID:
        fail("缺少 NOTION_DATABASE_ID，请检查 .env")

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
    resp = requests.get(url, headers=notion_headers(), timeout=20)

    if resp.status_code != 200:
        print(resp.text)
        fail("读取 Notion 数据库失败，请检查数据库 ID、Token、Connection 权限")

    return resp.json()


def find_title_property(properties: dict):
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    return None


def build_select_options(names):
    return [{"name": name, "color": "default"} for name in names]


def build_schema_patch(existing_properties: dict):
    patch = {}

    # 1. 重命名 Title 字段为「标题」
    title_prop_name = find_title_property(existing_properties)

    if not title_prop_name:
        fail("当前数据库没有 Title 类型字段。请确认你传入的是 Notion 数据库 ID，而不是普通页面 ID。")

    if title_prop_name != "标题":
        patch[title_prop_name] = {
            "name": "标题"
        }

    # 2. 需要创建的字段定义
    required_properties = {
        "原始链接": {
            "url": {}
        },
        "规范链接": {
            "url": {}
        },
        "来源平台": {
            "select": {
                "options": build_select_options([
                    "Web",
                    "小红书",
                    "B站",
                    "微信公众号",
                    "知乎",
                    "GitHub",
                    "论文",
                    "手动输入",
                    "其他",
                ])
            }
        },
        "内容类型": {
            "select": {
                "options": build_select_options([
                    "文章",
                    "视频",
                    "笔记",
                    "教程",
                    "论文",
                    "代码项目",
                    "灵感",
                    "工具",
                    "资料合集",
                    "其他",
                ])
            }
        },
        "一级分类": {
            "select": {
                "options": build_select_options([
                    "AI",
                    "编程开发",
                    "英语学习",
                    "金融财务",
                    "论文写作",
                    "工具效率",
                    "项目灵感",
                    "生活经验",
                    "职业发展",
                    "其他",
                ])
            }
        },
        "二级分类": {
            "select": {
                "options": build_select_options([
                    "Agent开发",
                    "Agent面试",
                    "大模型应用",
                    "Prompt工程",
                    "AI工具",
                    "机器学习",
                    "数据分析",
                    "前端开发",
                    "后端开发",
                    "数据库",
                    "DevOps",
                    "区块链开发",
                    "Python",
                    "Java",
                    "JavaScript",
                    "项目架构",
                    "测试运维",
                    "英语词汇",
                    "英语阅读",
                    "英语写作",
                    "财务分析",
                    "经营分析",
                    "论文资料",
                    "文献综述",
                    "写作方法",
                    "效率工具",
                    "知识管理",
                    "学习方法",
                    "产品设计",
                    "职业规划",
                    "面试求职",
                    "生活经验",
                    "未分类",
                ])
            }
        },
        "摘要": {
            "rich_text": {}
        },
        "关键词": {
            "multi_select": {
                "options": []
            }
        },
        "核心观点": {
            "rich_text": {}
        },
        "行动建议": {
            "rich_text": {}
        },
        "原文语言": {
            "select": {
                "options": build_select_options([
                    "中文",
                    "英文",
                    "其他",
                    "未知",
                ])
            }
        },
        "是否翻译": {
            "checkbox": {}
        },
        "阅读状态": {
            "select": {
                "options": build_select_options([
                    "未读",
                    "已读",
                    "精读",
                    "已归档",
                    "待处理",
                ])
            }
        },
        "重要程度": {
            "select": {
                "options": build_select_options([
                    "低",
                    "中",
                    "高",
                    "非常重要",
                ])
            }
        },
        "AI处理状态": {
            "select": {
                "options": build_select_options([
                    "已完成",
                    "失败",
                    "跳过",
                ])
            }
        },
        "创建时间": {
            "date": {}
        },
        "更新时间": {
            "date": {}
        },
    }

    # 3. 只创建缺失字段，已有字段不强制覆盖
    for name, schema in required_properties.items():
        if name not in existing_properties:
            patch[name] = schema

    return patch


def update_database_schema(patch: dict):
    if not patch:
        print("[OK] Notion 数据库字段已经完整，无需更新。")
        return

    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"

    payload = {
        "properties": patch
    }

    resp = requests.patch(
        url,
        headers=notion_headers(),
        json=payload,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(resp.text)
        fail("更新 Notion 数据库字段失败")

    print("[OK] Notion 数据库字段创建/更新成功。")
    print("本次更新字段：")
    for key in patch.keys():
        print(f"- {key}")


def main():
    print("[INFO] 正在读取 Notion 数据库...")
    database = get_database()

    properties = database.get("properties", {})
    print(f"[INFO] 当前数据库已有字段数量：{len(properties)}")

    patch = build_schema_patch(properties)

    print(f"[INFO] 需要创建/更新字段数量：{len(patch)}")

    update_database_schema(patch)

    print()
    print("[DONE] 请重新访问：")
    print("http://127.0.0.1:8000/api/notion/validate")
    print("如果 missing_fields 为空，就说明 Notion 字段已经配置完成。")


if __name__ == "__main__":
    main()