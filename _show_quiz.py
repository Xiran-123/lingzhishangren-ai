import json
data = json.load(open('knowledge_maps/knowledge_graph_v2.json', encoding='utf-8'))
g = data['graphs'][0]
for c in g['categories']:
    for n in c.get('nodes', []):
        if n.get('id') == 'phy_fourier':
            print('node:', n.get('name'))
            q = n.get('quiz', [])
            print('quiz count:', len(q))
            for i, qq in enumerate(q[:3]):
                qtype = qq.get('type', '?')
                stem = qq.get('question') or qq.get('stem') or str(qq)[:60]
                print(f'  [{i}] {qtype}: {stem}')
