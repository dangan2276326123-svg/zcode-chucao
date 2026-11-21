# -*- coding: utf-8 -*-
"""两份固件工程的分工守卫（2026-11-05，台账 Hw-34）。

作者裁定"新实车单独复制一份工程"，于是从这一天起仓里有两棵固件树：
`firmware/大车proj/大车`（上代车）与 `firmware/样机proj/样机`（新实车）。
复制本身没问题，错的是**它们悄悄漂**：改 retrofit 只改一份、改协议只改一份，
两辆车就跑两套逻辑，而编译照样 0 Error、台架也不一定看得出来。

这条测试把"哪些文件允许不同"写成白名单，其余必须逐字节相同——
漂了就在这里红，而不是等两辆车跑出两种行为。

允许不同的只有两份 + 两个 Keil 工程文件：

* `USER/main.c`：轮 4 的转向符号（新实车）——**这是本工程存在的理由**；
* `HARDWARE/retrofit/retrofit.h`：`PROFILE_ID` 指到 `PROFILE_REAL`；
* `USER/PWM.uvprojx`、`USER/PWM.uvoptx`：Keil 的工程/调试设置。

另外三条用例把这两处差异**钉死成具体的字串**，顺便守住"老工程没被顺手改掉"。
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD = os.path.join(REPO, 'firmware', '大车proj', '大车')
NEW = os.path.join(REPO, 'firmware', '样机proj', '样机')

# 相对工程根的白名单（正斜杠）
ALLOW_DIFF = {
    'USER/main.c',
    'HARDWARE/retrofit/retrofit.h',
    'USER/PWM.uvprojx',
    'USER/PWM.uvoptx',
}
# 构建产物 / 机器相关文件：不参与比对，也不要求两边都有
SKIP_DIRS = {'OBJ', 'DebugConfig'}
SKIP_SUFFIX = ('.uvguix.',)
# [zcode 审查修正 11-21] 合并后首跑在 zcode 机器上假红 2 例，根因即此。
# PWM.uvoptx 与 .uvguix 同类（Keil 调试选项，每次开工程都变）。它在老工程被
# git 历史跟踪、在新工程被 .gitignore 排除 ⇒ 跨机器的磁盘文件集必然不一致
# （11-21 在 zcode 机器上复现：老有新无）。按机器本地状态跳过，不进文件集比较。
SKIP_NAMES = {'build_log.txt', 'desktop.ini', 'PWM.uvoptx'}


def _walk(root):
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_NAMES or any(s in name for s in SKIP_SUFFIX):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root).replace('\\', '/')
            out.add(rel)
    return out


def _read(root, rel):
    """读盘并归一化 CRLF。

    磁盘字节对换行归一化敏感：同一 blob 在两棵树可能因检出时机不同而
    一边 CRLF 一边 LF（11-21 实测：protocol.c/ringbuffer.h/usart.c 三对
    blob 在 git 层 md5 全等、磁盘不等）。先归一化再比较，真内容漂移照样红，
    检出伪差不误报。
    """
    with open(os.path.join(root, rel), 'rb') as f:
        data = f.read()
    return data.replace(bytes([13, 10]), bytes([10]))

def test_both_projects_exist():
    assert os.path.isdir(OLD), OLD
    assert os.path.isdir(NEW), NEW


def test_same_file_set():
    """两棵树必须有同一套源文件——少一个文件就是少编进一段逻辑。"""
    only_old = sorted(_walk(OLD) - _walk(NEW))
    only_new = sorted(_walk(NEW) - _walk(OLD))
    assert not only_old, u'只在老工程里：%s' % only_old
    assert not only_new, u'只在新工程里：%s' % only_new


def test_only_allowlisted_files_differ():
    """除了白名单，任何字节的差异都算漂移（README 里写死的分工，这里执行它）。

    白名单是"允许不同"，不是"必须不同"——Keil 的 uvprojx/uvoptx 现在两边逐字一样，
    下次谁在 Keil 里存一下就可能变，那不算缺陷；算缺陷的是**没被允许的源文件**变了。
    """
    differing = {rel for rel in _walk(OLD) & _walk(NEW)
                 if _read(OLD, rel) != _read(NEW, rel)}
    unexpected = sorted(differing - ALLOW_DIFF)
    assert not unexpected, u'这些文件只改了一份工程：%s' % unexpected


def test_new_project_flips_wheel4_steering():
    """轮 4 = 作者编号 4 = 底盘左前 = angle[0] = 伺服地址 4（Hw-34）。

    实车两次读数把这条命令拆成三项（A 给角 / C-L 零位补偿 / B 90° 基准）：
    第一次整条取反后"遥控转向反了"，所以 A 必须回旧号（−1），B 保持同号（+1）；
    C-L 这一组不能动，它正是"上电静止四轮都直"的来源。谁把它们并回"整条翻"，
    这里就红——那是已经被实车否掉的形状。
    """
    body = _read(NEW, 'USER/main.c').decode('gbk', 'replace')
    assert 'send_angle(4,(W4_A_SIGN*angle[0]' in body
    assert '#define W4_A_SIGN  (-1.0)' in body
    assert '#define W4_B_SIGN  (+1.0)' in body
    assert 'send_angle(4,-(angle[0]-wheel_Angle_correct[0]' not in body


def test_old_project_keeps_the_old_wheel4_sign():
    """老工程必须保持逐字节不变（作者裁定：上代车那份不动）。"""
    body = _read(OLD, 'USER/main.c').decode('gbk', 'replace')
    assert 'send_angle(4,-(angle[0]-wheel_Angle_correct[0]' in body
    assert 'send_angle(4,(angle[0]+wheel_Angle_correct[0]' not in body


def test_profile_ids_differ_on_purpose():
    old_h = _read(OLD, 'HARDWARE/retrofit/retrofit.h').decode('gbk', 'replace')
    new_h = _read(NEW, 'HARDWARE/retrofit/retrofit.h').decode('gbk', 'replace')
    assert '#define PROFILE_ID   PROFILE_PREV' in old_h
    assert '#define PROFILE_ID   PROFILE_REAL' in new_h
