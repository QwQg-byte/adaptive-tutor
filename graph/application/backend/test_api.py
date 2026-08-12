import requests

base_url = "http://localhost:8000/api/v1"

# 测试不带筛选
print("=== 不带筛选 ===")
resp = requests.get(f"{base_url}/graph/questions", params={"page": 1, "page_size": 5})
data = resp.json()
if data.get('success'):
    for q in data['data']['questions'][:5]:
        print(f"  {q['id']}: {q['name'][:20]}... [{q['difficulty']}] {q['category1']}")

# 测试带分类筛选
print("\n=== 筛选 category1=语言基础 ===")
resp = requests.get(f"{base_url}/graph/questions", params={
    "page": 1, 
    "page_size": 5,
    "category1": "语言基础"
})
data = resp.json()
if data.get('success'):
    for q in data['data']['questions'][:5]:
        print(f"  {q['id']}: {q['name'][:20]}... [{q['difficulty']}] {q['category1']}")

# 测试带难度筛选
print("\n=== 筛选 difficulty=简单 ===")
resp = requests.get(f"{base_url}/graph/questions", params={
    "page": 1, 
    "page_size": 5,
    "difficulty": "简单"
})
data = resp.json()
if data.get('success'):
    for q in data['data']['questions'][:5]:
        print(f"  {q['id']}: {q['name'][:20]}... [{q['difficulty']}] {q['category1']}")
