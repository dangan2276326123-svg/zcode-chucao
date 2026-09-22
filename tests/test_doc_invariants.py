# -*- coding: utf-8 -*-
"""tools/check_doc_invariants.py 的测试。

最有价值的是 test_rule_examples_do_not_count：AGENTS 第 2 条里举着 `⑦–⑧` 这个反例，
若按"全仓"字面执行，规则会永远红——这正是 09-22 定案要按行块摘除的原因。
另有一条钉住"处＝出现次数"：同一行两次算两次，否则 6 行/7 次这个差会被当成漂移。
"""
import os

from tools import check_doc_invariants as cdi

EN, HY = '\u2013', '-'
BASE = cdi.BASELINE_FORM                      # ①–⑧
FORB = cdi.FORBIDDEN[1]                       # ⑦–⑧


def _write(root, name, text):
    p = os.path.join(str(root), name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


# ---------- 真仓 ----------
def test_real_repo_is_clean(tmp_path):
    counts, unreadable, scanned = cdi.enumerate_ranges(cdi.ROOT_DEFAULT)
    assert scanned >= 20, scanned
    assert not unreadable, unreadable
    for form in cdi.FORBIDDEN:
        assert counts[form] == [], (form, counts[form])
    code, msgs = cdi.verdict(counts, 7)
    assert code == 0, msgs


def test_rule_block_is_found_in_real_agents():
    lines = open(os.path.join(cdi.ROOT_DEFAULT, 'AGENTS.md'),
                 encoding='utf-8').read().split('\n')
    blk = cdi.find_rule_block(lines)
    assert blk is not None, 'AGENTS 里没找到第 2 条，检查器等于没在审计'
    a, b = blk
    assert '闭环核对' in lines[a]
    body = '\n'.join(lines[a:b])
    assert FORB in body, '前提不成立：第 2 条里已经没有反例，本测试要改'


# ---------- 摘除语义 ----------
def test_rule_examples_do_not_count(tmp_path):
    """第 2 条内的举例命中不算；同一条写在别处就算。"""
    agents = ('### 审查清单\n'
              '1. **事实核对**\n'
              '2. **闭环核对**：判读：`%s` 命中 7 处 = 基线；`%s` 恒为 0。\n'
              '   **补充**：09-21 的错形正是这条自己造的（%s 应为 %s）。\n'
              '3. **资产边界**\n' % (BASE, FORB, FORB, BASE))
    _write(tmp_path, 'AGENTS.md', agents)
    counts, unreadable, scanned = cdi.enumerate_ranges(tmp_path)
    assert scanned == 1 and not unreadable
    assert counts[FORB] == [], '第 2 条行块没摘掉：规则会永远红'
    assert counts[BASE] == [], '块内两处基线也该一起被摘除，否则基线数法说不清'

    # 块外出现同一串就必须抓到
    _write(tmp_path, 'docs/other.md', '这里写错了，应该是 %s 而不是 %s\n' % (BASE, FORB))
    counts2, _, _ = cdi.enumerate_ranges(tmp_path)
    assert counts2[FORB] and counts2[FORB][0][0].endswith('other.md')
    assert len(counts2[BASE]) == 1     # 只有块外那一次

    code, msgs = cdi.verdict(counts2, 7)
    assert code == 1 and any('禁用语义' in m for m in msgs)


def test_missing_rule_block_is_reported(tmp_path):
    _write(tmp_path, 'README.md', '没有审查清单的仓库\n')
    lines = open(os.path.join(str(tmp_path), 'README.md'), encoding='utf-8').read()
    assert cdi.find_rule_block(lines.split('\n')) is None


# ---------- 计数口径 ----------
def test_occurrence_not_line_counting(tmp_path):
    """同一行出现两次算 2 次；行数是另一个数。这是"7 处/6 行"歧义的钉桩。"""
    _write(tmp_path, 'x.md', '%s 和 %s 在同一行\n' % (BASE, BASE))
    counts, _, _ = cdi.enumerate_ranges(tmp_path)
    assert len(counts[BASE]) == 2
    assert len({h for h in counts[BASE]}) == 1


def test_baseline_drift_is_exit_2_not_1(tmp_path):
    counts = {f: [] for f in cdi.ALL_FORMS}
    code, msgs = cdi.verdict(counts, 7)
    assert code == 2 and any('必须解释' in m for m in msgs)
    assert '出现次数' in ' '.join(msgs), '漂移提示要说明数法，否则人会去改基线数字'

    code0, msgs0 = cdi.verdict(counts, 0)
    assert code0 == 0 and '通过' in msgs0[0]


def test_unreadable_file_is_not_silently_a_pass(tmp_path):
    """零命中如果来自"根本没读到文件"，那就是假通过——必须非零退出。"""
    p = os.path.join(str(tmp_path), 'broken.md')
    with open(p, 'wb') as f:
        f.write(b'\xff\xfe\x00invalid')
    counts, unreadable, scanned = cdi.enumerate_ranges(tmp_path)
    assert unreadable and scanned == 0
    assert counts[FORB] == []          # 没读到 ⇒ 没命中，这正是它危险的地方
