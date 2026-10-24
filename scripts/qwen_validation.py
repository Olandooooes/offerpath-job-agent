"""Conservative structural/source checks; human semantic review remains required."""
import hashlib
import json
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict(value, names):
    require(isinstance(value, dict) and set(value) == set(names), '字段缺失或包含不允许的批准/状态字段')


def text(value, limit):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, '内容为空、格式不正确或过长')
    require(not any(ord(c) < 32 and c not in '\n\r\t' for c in value), '内容含控制字符')
    return value.strip()


def numeric(claim, source):
    tokens = lambda s: set(re.findall(r'\d+(?:\.\d+)?%?', s))
    require(tokens(claim) <= tokens(source), '改写含引用事实中没有的数字；请先核实资料')


def validate(context, args):
    strict(args, ('context_id', 'summary', 'items', 'mapping', 'changes'))
    facts = {f['id']: f for f in context['facts']}
    items = args['items']
    require(isinstance(items, list) and 1 <= len(items) <= 3, '请返回1至3条相关经历')
    used, cleaned = set(), []
    for item in items:
        strict(item, ('fact_id', 'title', 'text'))
        identity = item['fact_id']
        require(isinstance(identity, str) and identity in facts and identity not in used, '引用了未选中、未知或重复的事实')
        title, claim = text(item['title'], 120), text(item['text'], 1000)
        require(title == facts[identity]['title'], '请保持所引用事实原标题')
        numeric(claim, facts[identity]['title'] + facts[identity]['details'])
        cleaned.append(dict(fact_id=identity, title=title, text=claim))
        used.add(identity)
    summary = args['summary']
    strict(summary, ('text', 'fact_ids'))
    refs = summary['fact_ids']
    require(isinstance(refs, list) and refs and all(isinstance(i, str) and i in used for i in refs) and len(set(refs)) == len(refs), '简介必须引用本版所选经历')
    summary_text = text(summary['text'], 450)
    numeric(summary_text, ' '.join(facts[i]['title'] + facts[i]['details'] for i in refs))
    requirements = context['job']['requirements']
    mapping, seen, gaps = args['mapping'], set(), []
    require(isinstance(mapping, list) and len(mapping) == len(requirements), '要求映射必须逐项完整')
    for row in mapping:
        strict(row, ('requirement_index', 'fact_id'))
        index, identity = row['requirement_index'], row['fact_id']
        require(type(index) is int and 0 <= index < len(requirements) and index not in seen, '岗位要求索引无效或重复')
        require(identity is None or isinstance(identity, str) and identity in used, '映射只能引用本版所选事实，缺口填null')
        seen.add(index)
        if identity is None:
            gaps.append(requirements[index])
    changes = args['changes']
    require(isinstance(changes, list) and 1 <= len(changes) <= 6, '请提供1至6条定制说明')
    return dict(summary=summary_text, summary_fact_ids=refs, items=cleaned, mapping=mapping,
                gaps=gaps, changes=[text(c, 300) for c in changes],
                input_hash=hashlib.sha256(json.dumps(args, ensure_ascii=False, sort_keys=True).encode()).hexdigest())
