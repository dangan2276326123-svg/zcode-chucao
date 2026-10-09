# -*- coding: utf-8 -*-
"""车辆档案加载（E3 spec §6）。

刻意不做"读不到就用默认值"：档案装的是换算量与安全许可位，
静默回默认等于让车带着错参数进无人。**读不到就报错停下。**
只用手写解析，不引 PyYAML 依赖（这个文件只有两个平铺的键）。
"""
import os

from common import protocol as P
from pc import wire

DEFAULT_PATH = os.path.join('config', 'vehicle_profile.yaml')
_VALID_PROFILE = (P.PROFILE_PREV, P.PROFILE_REAL)


def load(path=None):
    # 只有 **None** 才用默认档案。旧写法 `path = path or DEFAULT_PATH` 让空串 ''
    # 静默读到**另一台车**的换算量与许可位——那正好绕开本文件存在的全部理由
    # （Task 5 审查 P2）。调用层"未指定"一律传 None，'' 视作错误输入。
    if path is None:
        path = DEFAULT_PATH
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), path)
    if not os.path.exists(path):
        raise ValueError('车辆档案不存在：%s（spec §6：不许回默认值）' % path)

    kv = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                if not line or ':' not in line:
                    continue
                k, v = line.split(':', 1)
                kv[k.strip()] = v.strip()
    except OSError as e:
        # 契约在一处收口（Task 5 审查 P1）：exists() 为真但读不进去（路径是目录、
        # 编辑器锁文件、杀软占用、权限）也算"读不到"。PermissionError 是 OSError
        # 子类、**不是** ValueError，而调用方（pc/main.py）只 except ValueError
        # 来决定"能不能进无人"——漏出去就是一个崩溃而不是一条报错。
        # UnicodeDecodeError 不在这里接：它本来就是 ValueError 的子类。
        raise ValueError('车辆档案读不进去：%s（%s）' % (path, e)) from e

    try:
        profile_id = int(kv['profile_id'])
    except (KeyError, ValueError):
        raise ValueError('车辆档案缺 profile_id 或不是整数：%r' % kv.get('profile_id'))
    if profile_id not in _VALID_PROFILE:
        raise ValueError('profile_id 必须是 %s 之一，收到 %d' % (_VALID_PROFILE, profile_id))

    permit_name = kv.get('permit')
    if permit_name not in wire.PERMIT_BY_NAME:
        raise ValueError('permit 必须是 %s 之一，收到 %r'
                         % (sorted(wire.PERMIT_BY_NAME), permit_name))

    return {'profile_id': profile_id,
            'permit': wire.PERMIT_BY_NAME[permit_name],
            'path': path}
