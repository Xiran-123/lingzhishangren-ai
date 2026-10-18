# -*- coding: utf-8 -*-
"""本地批量解析岗位能力权重，结果保存到 parsed_results.json"""
import requests, json, time, re, os, sys

API_KEY = 'sk-sdfaoxkrbsmmnueekypiqjgxtcrscmrmajrzvtdjkgnjieyi'
API_URL = 'https://api.siliconflow.cn/v1/chat/completions'
MODEL_NAME = 'Pro/moonshotai/Kimi-K2.6'

COMPETENCE_AREAS = [
    {'id': 'signal_system', 'name': '信号与系统'},
    {'id': 'communication_principle', 'name': '通信原理'},
    {'id': 'digital_signal', 'name': '数字信号处理'},
    {'id': 'rf_engineering', 'name': '射频工程'},
    {'id': 'network_protocol', 'name': '网络协议'},
    {'id': 'antenna_design', 'name': '天线设计'},
    {'id': 'modulation', 'name': '调制技术'},
    {'id': 'troubleshooting', 'name': '故障排查'},
    {'id': 'equipment_operation', 'name': '设备操作'},
    {'id': 'safety_awareness', 'name': '安全意识'},
    {'id': 'teamwork', 'name': '团队协作'},
    {'id': 'innovation', 'name': '创新思维'},
]

dim_list = '\n'.join(f"{i+1}. {a['id']} - {a['name']}" for i, a in enumerate(COMPETENCE_AREAS))
SYS_PROMPT = (
    "你是通信工程岗位分析师。根据岗位描述，分析该岗位对通信工程学生12个能力维度的要求权重（0到1之间，0=不需要，1=极高要求）。\n"
    f"12个维度：\n{dim_list}\n\n"
    "严格只返回JSON，不要输出额外文字或markdown代码块，格式：\n"
    '{"competence_weights": {"signal_system": 0.8, "communication_principle": 0.9}, '
    '"required_skills": ["5G", "射频"], "career_type": "研发", "difficulty": "中高级"}'
)

def parse_job(title, desc, req, skills):
    user_prompt = f"岗位标题：{title}\n岗位描述：{desc[:500]}\n任职要求：{req[:500]}\n技能标签：{', '.join(skills[:10])}\n请分析并返回JSON。"
    try:
        start = time.time()
        resp = requests.post(
            API_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": SYS_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1000,
                "stream": False,
            },
            timeout=60,
        )
        elapsed = time.time() - start
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code} ({elapsed:.1f}s)")
            return None
        content = resp.json()["choices"][0]["message"]["content"].strip()
        m = re.search(r"\{.*\}", content, re.S)
        parsed = json.loads(m.group(0) if m else content)
        weights = parsed.get('competence_weights', {})
        for area in COMPETENCE_AREAS:
            if area['id'] not in weights:
                weights[area['id']] = 0.0
            try:
                weights[area['id']] = max(0.0, min(1.0, float(weights[area['id']])))
            except (TypeError, ValueError):
                weights[area['id']] = 0.0
        print(f"  OK ({elapsed:.1f}s)")
        return {
            'competence_weights': weights,
            'required_skills': parsed.get('required_skills', []),
            'career_type': parsed.get('career_type', ''),
            'difficulty': parsed.get('difficulty', ''),
        }
    except Exception as e:
        print(f"  FAIL: {e}")
        return None

def main():
    # 加载岗位数据
    with open(r'C:\Users\李昊\AppData\Local\Temp\jobs3.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    jobs = data.get('jobs', [])
    unparsed = [j for j in jobs if not j.get('parsed')]
    print(f"Total unparsed: {len(unparsed)}")

    # 加载已有的解析结果
    results_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parsed_results.json')
    if os.path.exists(results_file):
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    else:
        results = {}

    for i, job in enumerate(unparsed):
        job_id = job.get('id')
        if job_id in results:
            print(f"[{i+1}/{len(unparsed)}] {job.get('title')} - already done, skip")
            continue
        print(f"[{i+1}/{len(unparsed)}] {job.get('title')} | {job.get('company')}")
        result = parse_job(
            job.get('title', ''),
            job.get('description', ''),
            job.get('requirements', ''),
            job.get('skills', []),
        )
        if result:
            results[job_id] = result
            # 立即保存
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  Saved ({len(results)} total)")
        else:
            results[job_id] = None

    done = sum(1 for v in results.values() if v is not None)
    fail = sum(1 for v in results.values() if v is None)
    print(f"\nDone: {done}, Failed: {fail}, Total: {len(results)}")

if __name__ == '__main__':
    main()
