# -*- coding: utf-8 -*-
"""
因果故障链 + 难度自适应（Fault Chain & Adaptive Difficulty）

岗位场景任务智能生成 —— 两个核心能力：

1. 因果故障链
   注入单一故障表象 → 学生执行测试动作 → 因果链随排查深度动态展开：
   - 测试确认某分支 → 展开该分支的下一层子原因
   - 测试排除某分支 → 剪除该分支（标记已排除）
   - 到达叶子根因 → 提交根因诊断 + 处置方案 → 系统评分

2. 难度自适应
   三级难度：入门(1) / 工程师(2) / 专家(3)，同一场景随学员表现动态变形：
   - 入门：给分支排查提示、仅显示 Top3 高概率原因、不限时
   - 工程师：全量分支、提示可用但扣分
   - 专家：注入随机干扰测试、多故障并发（隐藏第二根因）、禁用提示、倒计时
   动态变形规则：
   - 连续误诊 ≥2 次 → 建议降级并解锁帮扶提示
   - 零误诊且测试次数逼近最优 → 建议升级（下局生效），专家局内会即时注入干扰变量
   每学生每域等级持久化到 data/fault_chain_state.json，等级变化由 app.py 写审计。

确定性规则引擎，不依赖 AI 即可完整运行；AI 仅作为导师答疑（SSE，ground 在当前链状态）。
"""

import json
import os
import uuid
from datetime import datetime, timedelta

DATA_DIR = "data"
STATE_FILE = os.path.join(DATA_DIR, "fault_chain_state.json")

LEVELS = {1: "入门", 2: "工程师", 3: "专家"}

# ============================ 因果图库 ============================
# 结构约定：
# - symptom: 故障表象（唯一入口）
# - nodes: 扁平节点表；parent 指向上层节点 id（"symptom" 表示第一层分支）
# - test: 鉴别测试。confirm_text/reject_text 为确定性结果；confirm_expands 为确认后展开的子节点
# - root: 仅根因叶子节点拥有；fixes 中 ok=True 为正确处置
# - expert_*: 专家级差异。expert_confirm_text/expert_expands 表示专家级该分支反而确认（多故障并发第二路径）
# - decoy_test: 专家级注入的干扰测试，结果含糊、不改变任何分支状态
# - par: 各难度下的最优测试次数（效率评分基准）

CAUSAL_CHAINS = {
    "base_station": {
        "domain": "base_station",
        "domain_label": "基站设备",
        "title": "基站覆盖骤降与掉话激增",
        "symptom": {
            "alarm": "网管告警：RRU 通道驻波比越限 + 小区 RSRP 均值下降 12dB",
            "scene": "某高校宿舍区 5G 基站覆盖骤降，学生集中投诉通话掉线、网速缓慢。",
            "known": "故障前夜有强降雨；该站近一周无施工记录；同机房其他小区正常。",
        },
        "par": {1: 4, 2: 3, 3: 5},
        "nodes": {
            "feeder": {
                "label": "馈线/接头链路异常", "parent": "symptom",
                "desc": "馈线进水、接头氧化或松动会导致驻波比恶化、覆盖收缩。",
                "hint": "驻波比告警优先怀疑天馈系统，先做驻波比定位测试。",
                "test": {
                    "id": "t_vswr", "name": "驻波比故障定位测试", "tool": "驻波比测试仪（SiteMaster）",
                    "confirm_text": "驻波比峰值出现在距机房 23m 处（接头 J2 位置），VSWR=3.8 → 确认天馈分支",
                    "reject_text": "全程驻波比 ≤1.3，天馈链路正常 → 排除",
                    "confirm_expands": ["joint_water", "joint_loose", "feeder_damage"],
                },
                "decoy_test": {
                    "id": "t_feeder_len", "name": "馈线长度与标签核对",
                    "result_text": "馈线长度 47.5m，标签模糊无法辨认批次，与台账存在 0.5m 出入（干扰信息：长度差异属测量误差，无诊断价值）",
                },
            },
            "joint_water": {
                "label": "接头 J2 进水受潮", "parent": "feeder",
                "desc": "降雨后接头防水胶泥老化，雨水渗入导致阻抗突变。",
                "hint": "故障前夜有强降雨，23m 处接头是露天走线，重点怀疑进水。",
                "test": {
                    "id": "t_j2_open", "name": "登塔检查接头 J2", "tool": "目视+绝缘电阻表",
                    "confirm_text": "接头防水胶泥开裂，内部有明显水渍，绝缘电阻 0.8MΩ（标准 ≥10MΩ） → 锁定根因",
                    "reject_text": "接头干燥、防水完好 → 排除",
                    "confirm_expands": ["root_j2"],
                },
            },
            "joint_loose": {
                "label": "接头紧固力矩不足", "parent": "feeder",
                "desc": "安装力矩不达标，振动后接触电阻增大。",
                "hint": "若无进水痕迹，可用力矩扳手复核。",
                "test": {
                    "id": "t_torque", "name": "接头力矩复核", "tool": "力矩扳手",
                    "confirm_text": "力矩低于标准 40% → 锁定根因",
                    "reject_text": "各接头力矩均在 18N·m 标准范围 → 排除",
                    "confirm_expands": [],
                },
            },
            "feeder_damage": {
                "label": "馈线本体机械损伤", "parent": "feeder",
                "desc": "馈线被外力挤压变形，特性阻抗不连续。",
                "hint": "沿馈线走线目视检查有无压扁、折弯。",
                "test": {
                    "id": "t_feeder_visual", "name": "馈线外观巡检", "tool": "目视+TDR",
                    "confirm_text": "发现馈线压扁变形点 → 锁定根因",
                    "reject_text": "馈线外观完好，TDR 波形无突变 → 排除",
                    "confirm_expands": [],
                },
            },
            "rru": {
                "label": "RRU 射频模块故障", "parent": "symptom",
                "desc": "RRU 功放增益下降或接收通道异常。",
                "hint": "驻波比告警指向天馈侧，RRU 本身故障概率较低，可查输出功率佐证。",
                "test": {
                    "id": "t_rru_power", "name": "RRU 输出功率回读", "tool": "网管性能计数器",
                    "confirm_text": "RRU 输出功率较配置值低 8dB → 确认 RRU 分支",
                    "reject_text": "RRU 各通道输出功率、接收电平均正常 → 排除 RRU 本体",
                    "confirm_expands": [],
                },
            },
            "config": {
                "label": "参数配置被误改", "parent": "symptom",
                "desc": "功率参数、邻区配置被误修改会导致覆盖异常。",
                "hint": "先查操作日志：近一周无施工记录，误改概率低。",
                "test": {
                    "id": "t_cfg_diff", "name": "配置快照比对", "tool": "网管配置管理",
                    "confirm_text": "发现功率参数被调低 → 确认配置分支",
                    "reject_text": "当前配置与故障前快照完全一致，操作日志无记录 → 排除",
                    "confirm_expands": [],
                },
            },
            "interference": {
                "label": "外部干扰源", "parent": "symptom",
                "desc": "新增干扰源（私装放大器、屏蔽器）抬升底噪。",
                "hint": "干扰通常抬升底噪但不变驻波比，与本次告警特征不符，可后查。",
                "test": {
                    "id": "t_spectrum", "name": "频谱扫描", "tool": "扫频仪",
                    "confirm_text": "发现异常干扰信号 → 确认干扰分支",
                    "reject_text": "底噪正常，无异常干扰信号 → 排除",
                    "confirm_expands": [],
                    "expert_confirm_text": "扫频发现 2.6GHz 频段底噪抬升 6dB，定位到宿舍楼某房间私装信号放大器 → 确认存在并发干扰源",
                    "expert_expands": ["root_amplifier"],
                },
            },
            "root_j2": {
                "label": "根因：接头 J2 进水", "parent": "joint_water",
                "desc": "降雨渗入防水老化接头，阻抗突变引发驻波告警与覆盖骤降。",
                "root": {
                    "cause": "接头 J2 防水胶泥老化开裂，强降雨后进水，绝缘下降、阻抗突变，导致驻波比越限与覆盖收缩。",
                    "fixes": [
                        {"id": "f_reseal", "name": "烘干接头并重做防水（胶泥+胶带+防水盒）", "ok": True,
                         "note": "正确：根除进水隐患，重做防水后驻波比恢复 ≤1.2"},
                        {"id": "f_tape", "name": "仅用胶带简单缠绕密封", "ok": False,
                         "note": "错误：胶带短期遮水，日晒后很快失效，属于临时敷衍"},
                        {"id": "f_power", "name": "提高小区发射功率补偿覆盖", "ok": False,
                         "note": "错误：掩盖根因，驻波反射加剧反而可能烧毁功放"},
                    ],
                },
            },
            "root_amplifier": {
                "label": "根因：私装信号放大器干扰", "parent": "interference",
                "desc": "宿舍内私装放大器抬升底噪，造成并发性掉话。",
                "root": {
                    "cause": "宿舍楼内私装信号放大器，上行底噪被抬升，与驻波故障并发叠加，掉话率进一步恶化。",
                    "fixes": [
                        {"id": "f_remove", "name": "协调拆除私装放大器并复测底噪", "ok": True,
                         "note": "正确：拆除干扰源后底噪恢复正常"},
                        {"id": "f_filter", "name": "加装滤波器压制干扰", "ok": False,
                         "note": "错误：滤波器无法消除同频放大器干扰，且增加插损"},
                        {"id": "f_ignore", "name": "暂不处理，优先修复驻波故障", "ok": False,
                         "note": "错误：干扰源持续存在，修复驻波后掉话仍超标"},
                    ],
                },
                "expert_only": True,
            },
        },
        "multi_fault_level": 3,
        "secondary_root": "root_amplifier",
        "secondary_entry": "interference",
    },

    "transmission": {
        "domain": "transmission",
        "domain_label": "传输网络",
        "title": "OTN 链路误码率突增",
        "symptom": {
            "alarm": "网管告警：OTN 波道 BER 从 10⁻¹² 恶化至 10⁻⁵，FEC 纠错计数暴涨",
            "scene": "汇聚机房至核心机房的 100G 波分链路误码率突增，承载业务出现丢包。",
            "known": "昨夜机房空调一度故障，室温升至 35℃；光缆路由近期无施工。",
        },
        "par": {1: 4, 2: 3, 3: 5},
        "nodes": {
            "optic_module": {
                "label": "光模块性能劣化", "parent": "symptom",
                "desc": "光模块激光器老化、温度漂移导致出光功率/消光比异常。",
                "hint": "高温环境是光模块劣化的典型诱因，先读 DDM 数字诊断信息。",
                "test": {
                    "id": "t_ddm", "name": "光模块 DDM 诊断读取", "tool": "网管 DDM 监控",
                    "confirm_text": "本端光模块温度 78℃（门限 70℃），发射功率漂移 -2.3dB → 确认光模块分支",
                    "reject_text": "温度、功率、偏置电流均在正常范围 → 排除",
                    "confirm_expands": ["module_aging", "module_heat"],
                },
            },
            "module_heat": {
                "label": "高温致光模块温漂", "parent": "optic_module",
                "desc": "机房空调故障期间光模块长期高温，激光器波长漂移、输出劣化。",
                "hint": "昨夜空调故障室温 35℃，与告警时间高度吻合。",
                "test": {
                    "id": "t_module_swap", "name": "更换同型号光模块对比", "tool": "备件光模块",
                    "confirm_text": "更换后 BER 立即恢复 10⁻¹² → 锁定根因：原光模块高温劣化",
                    "reject_text": "更换后误码无改善 → 排除光模块",
                    "confirm_expands": ["root_module"],
                },
            },
            "module_aging": {
                "label": "光模块自然老化", "parent": "optic_module",
                "desc": "光模块服役超 5 年，激光器缓慢劣化。",
                "hint": "查模块入网时间，若不足两年则老化概率低。",
                "test": {
                    "id": "t_module_age", "name": "光模块服役年限核查", "tool": "台账+序列号",
                    "confirm_text": "模块已服役 6 年 → 支持老化判断",
                    "reject_text": "模块入网仅 14 个月，远未到老化期 → 排除自然老化",
                    "confirm_expands": [],
                },
            },
            "fiber": {
                "label": "光缆线路劣化", "parent": "symptom",
                "desc": "光缆衰耗增大、连接器污染导致接收光功率不足。",
                "hint": "无施工记录则光缆损伤概率低，可先测收光功率。",
                "test": {
                    "id": "t_rxpower", "name": "收光功率测试", "tool": "光功率计",
                    "confirm_text": "收光功率低于灵敏度 → 确认线路分支",
                    "reject_text": "收光功率 -8.2dBm，处于设计范围（-5~-14dBm）→ 排除线路衰耗问题",
                    "confirm_expands": ["fiber_connector", "fiber_bend"],
                },
            },
            "fiber_connector": {
                "label": "连接器端面污染", "parent": "fiber",
                "desc": "跳纤端面灰尘/油污引入额外衰耗与反射。",
                "hint": "用端面显微镜检查跳纤头。",
                "test": {
                    "id": "t_endface", "name": "端面显微检查", "tool": "光纤显微镜",
                    "confirm_text": "端面明显污染 → 清洁后复测",
                    "reject_text": "端面洁净 → 排除",
                    "confirm_expands": [],
                },
            },
            "fiber_bend": {
                "label": "光纤弯曲半径过小", "parent": "fiber",
                "desc": "ODF 架内跳纤被压折，宏弯衰耗增大。",
                "hint": "检查 ODF 架内跳纤盘留是否规范。",
                "test": {
                    "id": "t_odf", "name": "ODF 架内跳纤检查", "tool": "目视",
                    "confirm_text": "发现压折点 → 整理后复测",
                    "reject_text": "盘留规范无压折 → 排除",
                    "confirm_expands": [],
                },
            },
            "wss": {
                "label": "合分波器件/WSS 异常", "parent": "symptom",
                "desc": "合分波板卡通道插损漂移影响特定波道。",
                "hint": "若只有单个波道误码恶化，合分波器件嫌疑上升。",
                "test": {
                    "id": "t_wss", "name": "各波道功率均衡性检查", "tool": "网管波道监控",
                    "confirm_text": "目标波道功率明显偏离 → 确认器件分支",
                    "reject_text": "各波道功率均衡，仅本波道误码高 → 排除公共器件",
                    "confirm_expands": [],
                    "expert_confirm_text": "排查中发现并发管理缺陷：温度传感器未接入网管联动，高温持续 6 小时无人知晓 → 确认存在管理层并发根因",
                    "expert_expands": ["root_temp_alarm"],
                },
            },
            "root_module": {
                "label": "根因：光模块高温劣化", "parent": "module_heat",
                "desc": "空调故障高温导致光模块激光器不可逆劣化。",
                "root": {
                    "cause": "机房空调故障期间环境温度 35℃，光模块长期高温运行，激光器发生不可逆劣化，出光功率漂移引发误码率恶化。",
                    "fixes": [
                        {"id": "f_replace", "name": "更换光模块，并修复空调、加装温度告警联动", "ok": True,
                         "note": "正确：换件除根因，修复空调+告警联动防复发"},
                        {"id": "f_fec", "name": "提高 FEC 纠错等级容忍误码", "ok": False,
                         "note": "错误：只压制表象，劣化模块会继续恶化直至断链"},
                        {"id": "f_clean", "name": "清洁光模块端面后继续使用", "ok": False,
                         "note": "错误：劣化在激光器内部，清洁端面无济于事"},
                    ],
                },
            },
            "root_temp_alarm": {
                "label": "根因：温度监控缺失", "parent": "wss",
                "desc": "并发管理缺陷：高温未触发任何联动告警。",
                "root": {
                    "cause": "机房温度传感器未接入网管联动，空调故障期间高温持续 6 小时无人知晓，是光模块劣化的管理层根因。",
                    "fixes": [
                        {"id": "f_linkage", "name": "温度传感器接入网管并设联动告警", "ok": True,
                         "note": "正确：堵住管理漏洞，高温即时告警"},
                        {"id": "f_patrol", "name": "增加人工巡视频次", "ok": False,
                         "note": "错误：夜间无人值守时段仍存在监控空窗"},
                        {"id": "f_nothing", "name": "不作处理，属偶发事件", "ok": False,
                         "note": "错误：空调故障必然复发，风险敞口未关闭"},
                    ],
                },
                "expert_only": True,
            },
        },
        "multi_fault_level": 3,
        "secondary_root": "root_temp_alarm",
        "secondary_entry": "wss",
    },

    "core_network": {
        "domain": "core_network",
        "domain_label": "核心网",
        "title": "用户附着成功率骤降",
        "symptom": {
            "alarm": "KPI 告警：EPS 附着成功率从 99.2% 跌至 91.5%，失败原因值集中于 ESM cause #19",
            "scene": "早高峰期间大量用户投诉手机无信号、无法注册网络，MME 附着失败计数暴涨。",
            "known": "昨夜 MME 进行过补丁升级；HSS 侧无告警；无线侧 KPI 正常。",
        },
        "par": {1: 4, 2: 3, 3: 5},
        "nodes": {
            "mme_patch": {
                "label": "MME 补丁引入缺陷", "parent": "symptom",
                "desc": "昨夜升级的补丁可能改变了鉴权流程处理逻辑。",
                "hint": "故障紧随补丁升级出现，时间相关性极强，优先回退验证。",
                "test": {
                    "id": "t_rollback", "name": "补丁回退灰度验证", "tool": "MME 维护终端",
                    "confirm_text": "回退后测试 USIM 附着全部成功 → 确认补丁缺陷分支",
                    "reject_text": "回退后失败依旧 → 排除补丁因素",
                    "confirm_expands": ["auth_flow", "root_patch"],
                },
            },
            "auth_flow": {
                "label": "鉴权向量处理异常", "parent": "mme_patch",
                "desc": "补丁错误处理 ESM cause #19 场景下的鉴权重同步流程。",
                "hint": "抓取失败用户的完整信令，看卡在哪条消息。",
                "test": {
                    "id": "t_trace", "name": "失败用户信令跟踪", "tool": "信令监测系统",
                    "confirm_text": "信令显示 UE 回复 AUTS 重同步后，MME 未正确重取鉴权向量，直接拒绝 → 锁定根因",
                    "reject_text": "鉴权流程完整，失败在后续承载建立 → 转移分支",
                    "confirm_expands": ["root_patch"],
                },
            },
            "hss": {
                "label": "HSS 用户数据异常", "parent": "symptom",
                "desc": "HSS 签约数据损坏或容量受限导致鉴权失败。",
                "hint": "HSS 无告警且失败集中在补丁升级后，概率较低。",
                "test": {
                    "id": "t_hss_query", "name": "HSS 签约数据抽查", "tool": "HSS 维护台",
                    "confirm_text": "发现批量签约数据异常 → 确认 HSS 分支",
                    "reject_text": "抽查 50 个失败用户签约数据完整一致 → 排除 HSS",
                    "confirm_expands": [],
                },
            },
            "dns": {
                "label": "DNS 解析异常", "parent": "symptom",
                "desc": "MME 解析 HSS/网关地址失败导致流程中断。",
                "hint": "DNS 故障通常伴随解析超时告警，与 #19 原因值不符。",
                "test": {
                    "id": "t_dns", "name": "DNS 解析测试", "tool": "DNS 诊断命令",
                    "confirm_text": "解析超时 → 确认 DNS 分支",
                    "reject_text": "解析全部正常，时延 <5ms → 排除",
                    "confirm_expands": [],
                },
            },
            "capacity": {
                "label": "MME 容量过载", "parent": "symptom",
                "desc": "早高峰信令风暴导致 MME CPU 过载丢弃消息。",
                "hint": "过载失败通常伴随 CPU 告警且原因值分散，本次原因值集中在 #19。",
                "test": {
                    "id": "t_cpu", "name": "MME 负荷检查", "tool": "性能监控",
                    "confirm_text": "CPU 持续 95% 以上 → 确认过载分支",
                    "reject_text": "CPU 峰值 62%，内存正常，无丢包计数 → 排除过载",
                    "confirm_expands": [],
                    "expert_confirm_text": "负荷正常，但复盘升级流程发现并发管理缺陷：补丁未经灰度验证直接全量部署 → 确认管理层并发根因",
                    "expert_expands": ["root_gray"],
                },
            },
            "root_patch": {
                "label": "根因：补丁鉴权重同步缺陷", "parent": "auth_flow",
                "desc": "补丁未正确处理 AUTS 重同步流程。",
                "root": {
                    "cause": "MME 补丁存在缺陷：收到 UE 的 AUTS 重同步请求后未向 HSS 重新获取鉴权向量，直接以 ESM #19 拒绝，导致部分 USIM 附着失败。",
                    "fixes": [
                        {"id": "f_rollback", "name": "全网回退补丁，向厂家上报缺陷并跟踪修复版本", "ok": True,
                         "note": "正确：回退立即恢复业务，缺陷闭环到厂家"},
                        {"id": "f_restart", "name": "定时重启 MME 缓解", "ok": False,
                         "note": "错误：重启不解决逻辑缺陷，反而增加业务中断"},
                        {"id": "f_usim", "name": "批量更换用户 USIM 卡", "ok": False,
                         "note": "错误：问题在 MME 侧，换卡无效且成本巨大"},
                    ],
                },
            },
            "root_gray": {
                "label": "根因：升级流程缺失灰度", "parent": "capacity",
                "desc": "管理根因：补丁未做灰度验证直接全量升级。",
                "root": {
                    "cause": "升级管理流程缺陷：补丁未经灰度环境验证直接全量部署，缺陷未被提前暴露。",
                    "fixes": [
                        {"id": "f_gray", "name": "建立补丁灰度验证流程（先单节点试点 48h）", "ok": True,
                         "note": "正确：流程堵漏，缺陷在灰度期即可暴露"},
                        {"id": "f_night", "name": "以后改在深夜升级", "ok": False,
                         "note": "错误：改时间不验证，缺陷补丁照样全量生效"},
                        {"id": "f_vendor", "name": "要求厂家保证补丁质量", "ok": False,
                         "note": "错误：外部约束无法替代内部验证流程"},
                    ],
                },
                "expert_only": True,
            },
        },
        "multi_fault_level": 3,
        "secondary_root": "root_gray",
        "secondary_entry": "capacity",
    },

    "power": {
        "domain": "power",
        "domain_label": "通信电源",
        "title": "市电闪断后基站批量退服",
        "symptom": {
            "alarm": "动环告警：市电闪断 300ms，UPS 转旁路失败，3 个 BBU 下电重启",
            "scene": "雷暴天气市电闪断，机房内多台设备异常重启，部分基站退服超 10 分钟。",
            "known": "UPS 蓄电池组已运行 4 年；上月例行放电测试结果合格；闪断伴随一次近雷。",
        },
        "par": {1: 4, 2: 3, 3: 5},
        "nodes": {
            "ups_bypass": {
                "label": "UPS 旁路切换失败", "parent": "symptom",
                "desc": "市电闪断瞬间 UPS 未能完成逆变/旁路切换，输出中断。",
                "hint": "核心疑点：为什么 300ms 闪断会导致下电？查 UPS 事件日志。",
                "test": {
                    "id": "t_ups_log", "name": "UPS 事件日志提取", "tool": "UPS 监控面板",
                    "confirm_text": "日志显示闪断瞬间逆变器 IGBT 保护动作，旁路静态开关未闭合 → 确认 UPS 分支",
                    "reject_text": "日志显示切换正常完成 → 排除 UPS 本体",
                    "confirm_expands": ["igbt", "bypass_switch", "root_igbt"],
                },
            },
            "igbt": {
                "label": "逆变器 IGBT 过流保护", "parent": "ups_bypass",
                "desc": "雷击浪涌经市电窜入，逆变器 IGBT 过流保护停机。",
                "hint": "闪断伴随近雷，浪涌是 IGBT 保护的常见诱因。",
                "test": {
                    "id": "t_surge", "name": "浪涌保护器（SPD）状态检查", "tool": "目视+SPD 计数器",
                    "confirm_text": "输入侧 SPD 动作计数 +1，窗口变红，浪涌确曾窜入 → 锁定根因链条",
                    "reject_text": "SPD 无动作记录 → 浪涌假设存疑",
                    "confirm_expands": ["root_igbt"],
                },
            },
            "bypass_switch": {
                "label": "静态旁路开关失效", "parent": "ups_bypass",
                "desc": "旁路静态开关故障导致无法兜底。",
                "hint": "手动执行一次旁路切换测试验证。",
                "test": {
                    "id": "t_bypass_test", "name": "旁路切换功能测试", "tool": "UPS 测试模式",
                    "confirm_text": "旁路切换失败 → 锁定开关故障",
                    "reject_text": "测试模式下旁路切换正常，属于逆变器先停机导致的连锁 → 排除开关本体",
                    "confirm_expands": [],
                },
            },
            "battery": {
                "label": "蓄电池组失效", "parent": "symptom",
                "desc": "电池老化内阻增大，放电瞬间电压崩塌。",
                "hint": "电池运行 4 年有嫌疑，但上月放电测试合格，先做内阻快测。",
                "test": {
                    "id": "t_internal_r", "name": "蓄电池内阻测试", "tool": "内阻测试仪",
                    "confirm_text": "多节电池内阻超标 → 确认电池分支",
                    "reject_text": "各节内阻与上月基线一致，组压正常 → 排除电池（上月合格记录属实）",
                    "confirm_expands": [],
                },
                "decoy_test": {
                    "id": "t_battery_look", "name": "电池外观检查",
                    "result_text": "电池壳体轻微鼓胀痕迹（干扰信息：为早期正常形变记录，与本次闪断下电无因果关联）",
                },
            },
            "dc_dist": {
                "label": "直流配电空开跳闸", "parent": "symptom",
                "desc": "直流分配柜空开过流跳闸导致 BBU 下电。",
                "hint": "检查配电柜各空开位置状态。",
                "test": {
                    "id": "t_breaker", "name": "配电柜空开状态检查", "tool": "目视+万用表",
                    "confirm_text": "发现跳闸空开 → 确认配电分支",
                    "reject_text": "全部空开在合位，下电发生在 UPS 输出侧上游 → 排除",
                    "confirm_expands": [],
                    "expert_confirm_text": "空开正常，但实测机房接地电阻 8.5Ω（标准 ≤4Ω），浪涌泄放不畅 → 确认并发隐患根因",
                    "expert_expands": ["root_ground"],
                },
            },
            "root_igbt": {
                "label": "根因：浪涌致 IGBT 保护停机", "parent": "igbt",
                "desc": "雷击浪涌窜入 → 逆变器保护停机 → 输出中断。",
                "root": {
                    "cause": "近雷浪涌经市电窜入，UPS 逆变器 IGBT 过流保护停机，300ms 内旁路未能接管，造成输出中断、BBU 下电重启。",
                    "fixes": [
                        {"id": "f_spd", "name": "更换动作后的 SPD，UPS 输入侧升级为二级浪涌防护", "ok": True,
                         "note": "正确：拦截浪涌路径，防止 IGBT 再次保护停机"},
                        {"id": "f_battery", "name": "整体更换蓄电池组", "ok": False,
                         "note": "错误：电池测试合格，换电池不解决浪涌窜入问题"},
                        {"id": "f_reset", "name": "复位 UPS 告警后恢复运行", "ok": False,
                         "note": "错误：浪涌路径未封堵，下次雷暴必然重演"},
                    ],
                },
            },
            "root_ground": {
                "label": "根因：接地电阻超标", "parent": "dc_dist",
                "desc": "并发隐患：机房接地电阻超标放大浪涌危害。",
                "root": {
                    "cause": "机房接地体锈蚀，接地电阻 8.5Ω（标准 ≤4Ω），浪涌泄放不畅，放大了对 UPS 的冲击。",
                    "fixes": [
                        {"id": "f_ground", "name": "重做接地网，接地电阻降至 4Ω 以下", "ok": True,
                         "note": "正确：恢复浪涌泄放通道"},
                        {"id": "f_wire", "name": "加粗设备接地线", "ok": False,
                         "note": "错误：瓶颈在接地体而非引线"},
                        {"id": "f_ignore", "name": "记录待明年大修", "ok": False,
                         "note": "错误：雷雨季节风险敞口不可接受"},
                    ],
                },
                "expert_only": True,
            },
        },
        "multi_fault_level": 3,
        "secondary_root": "root_ground",
        "secondary_entry": "dc_dist",
    },

    "network_opt": {
        "domain": "network_opt",
        "domain_label": "网络优化",
        "title": "密集城区切换成功率恶化",
        "symptom": {
            "alarm": "KPI 告警：LTE 切换成功率从 98.5% 跌至 93.1%，掉话率同步上升",
            "scene": "中央商务区早高峰切换失败激增，用户投诉通话中断，集中在两栋写字楼之间路段。",
            "known": "上周新开通一个微站；周边宏站参数近期无变更；投诉路段处于三个小区交界。",
        },
        "par": {1: 4, 2: 3, 3: 5},
        "nodes": {
            "neighbor": {
                "label": "邻区关系漏配", "parent": "symptom",
                "desc": "新开通微站与周边宏站邻区关系未完整配置。",
                "hint": "新站入网后邻区漏配是切换失败的经典原因，先查新微站邻区表。",
                "test": {
                    "id": "t_neighbor", "name": "新微站邻区配置核查", "tool": "网管邻区管理",
                    "confirm_text": "微站与投诉路段主服务宏站之间邻区关系缺失（应配 6 对实配 4 对） → 确认邻区分支",
                    "reject_text": "邻区配置完整无遗漏 → 排除",
                    "confirm_expands": ["root_neighbor"],
                },
            },
            "handover_param": {
                "label": "切换门限参数不当", "parent": "symptom",
                "desc": "A3 偏移、迟滞参数设置不合理导致切换过迟。",
                "hint": "宏站参数近期无变更记录，可后置排查。",
                "test": {
                    "id": "t_ho_param", "name": "切换参数核查", "tool": "网管参数管理",
                    "confirm_text": "发现门限被调得过高 → 确认参数分支",
                    "reject_text": "A3 偏移/迟滞/触发时长均为优化基线值 → 排除",
                    "confirm_expands": [],
                    "expert_confirm_text": "参数正常，但复盘新站入网流程发现并发管理缺陷：入网缺少切换性能验收环节 → 确认管理层并发根因",
                    "expert_expands": ["root_process"],
                },
            },
            "pilot_pollution": {
                "label": "导频污染", "parent": "symptom",
                "desc": "多小区信号交叠，无主服务小区导致频繁切换。",
                "hint": "三小区交界路段历来是导频污染高发区，可路测验证。",
                "test": {
                    "id": "t_dt", "name": "投诉路段路测", "tool": "路测终端（TEMS）",
                    "confirm_text": "路段同时收到 4 个 RSRP 相近小区 → 确认导频污染",
                    "reject_text": "主服务小区清晰，RSRP 领先邻区 6dB 以上 → 排除",
                    "confirm_expands": [],
                },
                "decoy_test": {
                    "id": "t_cqi", "name": "CQI 均值统计调取",
                    "result_text": "投诉区域 CQI 均值 11.2，略低于全网均值 11.8（干扰信息：轻微差异在噪声范围内，不指向任何分支）",
                },
            },
            "new_site_fault": {
                "label": "新微站硬件故障", "parent": "symptom",
                "desc": "新站设备隐性故障导致切换入失败。",
                "hint": "新站若有硬件故障通常伴随告警，可先查告警台。",
                "test": {
                    "id": "t_newsite_alarm", "name": "新微站告警与性能核查", "tool": "网管告警台",
                    "confirm_text": "发现通道异常告警 → 确认硬件分支",
                    "reject_text": "新站无任何告警，各项 KPI 正常 → 排除",
                    "confirm_expands": [],
                },
            },
            "root_neighbor": {
                "label": "根因：邻区漏配", "parent": "neighbor",
                "desc": "新站入网流程邻区配置环节遗漏。",
                "root": {
                    "cause": "新微站开通时邻区关系配置遗漏 2 对（与投诉路段主服务宏站双向漏配），切换目标小区不在邻区表内，测量报告触发不了切换，导致拖尾掉话。",
                    "fixes": [
                        {"id": "f_add", "name": "补齐漏配邻区并开启 ANR 自动邻区优化", "ok": True,
                         "note": "正确：补齐邻区+ANR 防人工遗漏"},
                        {"id": "f_power", "name": "抬高宏站功率压过微站", "ok": False,
                         "note": "错误：加剧干扰且微站覆盖区形成新盲区"},
                        {"id": "f_lock", "name": "锁定用户驻留宏站禁止切换", "ok": False,
                         "note": "错误：移动用户出宏站覆盖直接掉话，后果更严重"},
                    ],
                },
            },
            "root_process": {
                "label": "根因：新站入网验收缺失", "parent": "handover_param",
                "desc": "管理根因：新站入网无切换验收环节。",
                "root": {
                    "cause": "新站入网流程缺少切换性能验收测试环节，邻区漏配未能在入网前暴露。",
                    "fixes": [
                        {"id": "f_accept", "name": "入网流程增加切换验收路测（必测项）", "ok": True,
                         "note": "正确：流程堵漏，同类问题入网前拦截"},
                        {"id": "f_doc", "name": "发文要求以后注意", "ok": False,
                         "note": "错误：无强制校验环节的提醒形同虚设"},
                        {"id": "f_punish", "name": "考核责任人", "ok": False,
                         "note": "错误：不修补流程，换人仍会遗漏"},
                    ],
                },
                "expert_only": True,
            },
        },
        "multi_fault_level": 3,
        "secondary_root": "root_process",
        "secondary_entry": "handover_param",
    },
}

DOMAIN_LABELS = {k: v["domain_label"] for k, v in CAUSAL_CHAINS.items()}

# 难度规则说明（用于前端展示与导师上下文）
LEVEL_RULES = {
    1: {"label": "入门", "hints": True, "top_n": 3, "time_limit": None,
        "decoys": False, "multi_fault": False,
        "desc": "显示分支排查提示，优先展示 Top3 高概率原因，不限时"},
    2: {"label": "工程师", "hints": True, "top_n": None, "time_limit": None,
        "decoys": False, "multi_fault": False,
        "desc": "全量分支自主排查，提示可用但每次扣 5 分"},
    3: {"label": "专家", "hints": False, "top_n": None, "time_limit": 600,
        "decoys": True, "multi_fault": True,
        "desc": "注入干扰信息、多故障并发、禁用提示、限时 10 分钟"},
}

# 评分权重
SCORE_ROOT = 40        # 根因诊断（专家级双根因各 20）
SCORE_FIX = 20         # 处置方案
SCORE_EFFICIENCY = 30  # 测试效率（最优次数/实际次数）
SCORE_NO_MISDIAG = 10  # 零误诊加分
PENALTY_MISDIAG = 8    # 每次误诊扣分
PENALTY_HINT = 5       # 每次提示扣分
PENALTY_TIMEOUT = 10   # 超时扣分（效率分同时清零）


# ============================ 基础工具 ============================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)


def init_fault_chain_data():
    """初始化状态文件（首次运行自动创建）"""
    _ensure_dir()
    if not os.path.exists(STATE_FILE):
        _save({"version": 1, "created_at": _now(), "updated_at": _now(),
               "levels": {}, "sessions": {}, "history": []})


def _load() -> dict:
    _ensure_dir()
    if not os.path.exists(STATE_FILE):
        return {"version": 1, "created_at": _now(), "updated_at": _now(),
                "levels": {}, "sessions": {}, "history": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("状态文件结构异常")
        data.setdefault("levels", {})
        data.setdefault("sessions", {})
        data.setdefault("history", [])
        return data
    except Exception as e:
        print(f"[故障链] 状态读取失败，使用空状态: {e}")
        return {"version": 1, "created_at": _now(), "updated_at": _now(),
                "levels": {}, "sessions": {}, "history": []}


def _save(data: dict):
    """原子写入，避免中途崩溃损坏状态"""
    _ensure_dir()
    data["updated_at"] = _now()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def _get_chain(domain: str):
    return CAUSAL_CHAINS.get(domain)


# ============================ 难度自适应 ============================

def get_student_level(student_no: str, domain: str) -> int:
    """学生在该域的当前难度等级（默认入门）"""
    data = _load()
    return int(data.get("levels", {}).get(str(student_no), {}).get(domain, 1))


def set_student_level(student_no: str, domain: str, level: int) -> dict:
    """调整等级，返回 before/after 供审计"""
    level = max(1, min(3, int(level)))
    data = _load()
    stu = data.setdefault("levels", {}).setdefault(str(student_no), {})
    before = int(stu.get(domain, 1))
    stu[domain] = level
    _save(data)
    return {"student_no": str(student_no), "domain": domain,
            "before": before, "after": level}


def get_student_levels(student_no: str) -> dict:
    """某学生全部域的等级"""
    data = _load()
    raw = data.get("levels", {}).get(str(student_no), {})
    return {d: {"level": int(raw.get(d, 1)), "level_label": LEVELS[int(raw.get(d, 1))]}
            for d in CAUSAL_CHAINS}


def _level_rules(level: int) -> dict:
    return LEVEL_RULES.get(level, LEVEL_RULES[1])


# ============================ 会话引擎 ============================

def _visible_nodes(sess: dict) -> list:
    """当前可见（未剪除）的候选节点"""
    chain = _get_chain(sess["domain"])
    rules = _level_rules(sess["level"])
    out = []
    for nid in sess["revealed"]:
        if nid in sess["pruned"] or nid in sess["confirmed_roots"]:
            continue
        node = chain["nodes"].get(nid)
        if not node:
            continue
        if node.get("expert_only") and sess["level"] < 3:
            continue
        out.append(nid)
    # 入门级：仅保留 Top3 高概率原因（第一层按库中顺序视为先验概率排序）
    top_n = rules.get("top_n")
    if top_n and sess["depth"] == 0:
        l1 = [nid for nid in out if chain["nodes"][nid].get("parent") == "symptom"]
        deeper = [nid for nid in out if nid not in l1]
        out = l1[:top_n] + deeper
    return out


def _node_public(sess: dict, nid: str) -> dict:
    """节点对外视图（不泄露正确答案）"""
    chain = _get_chain(sess["domain"])
    node = chain["nodes"][nid]
    rules = _level_rules(sess["level"])
    item = {
        "id": nid,
        "label": node["label"],
        "desc": node["desc"],
        "parent": node.get("parent", ""),
        "is_root": bool(node.get("root")),
        "hint": (node.get("hint", "") if rules.get("hints") else ""),
        "test": None,
        "decoy_test": None,
    }
    if node.get("test"):
        t = node["test"]
        item["test"] = {"id": t["id"], "name": t["name"], "tool": t.get("tool", "")}
    if node.get("root"):
        # 处置选项对外可见，但不泄露正确性标记
        item["fixes"] = [{"id": f["id"], "name": f["name"]} for f in node["root"]["fixes"]]
        item["cause_preview"] = node["desc"]
    if rules.get("decoys") and node.get("decoy_test"):
        d = node["decoy_test"]
        item["decoy_test"] = {"id": d["id"], "name": d["name"], "tool": "现场记录"}
    return item


def _session_public(sess: dict) -> dict:
    """会话对外视图"""
    chain = _get_chain(sess["domain"])
    rules = _level_rules(sess["level"])
    visible = [_node_public(sess, nid) for nid in _visible_nodes(sess)]
    confirmed_path = []
    for nid in sess["confirmed_path"]:
        node = chain["nodes"].get(nid)
        if node:
            confirmed_path.append({"id": nid, "label": node["label"]})
    pruned = []
    for nid in sess["pruned"]:
        node = chain["nodes"].get(nid)
        if node:
            pruned.append({"id": nid, "label": node["label"]})
    remaining = None
    if sess.get("deadline"):
        remaining = max(0, int((datetime.strptime(sess["deadline"], "%Y-%m-%d %H:%M:%S")
                                - datetime.now()).total_seconds()))
    return {
        "session_id": sess["session_id"],
        "domain": sess["domain"],
        "domain_label": chain["domain_label"],
        "title": chain["title"],
        "level": sess["level"],
        "level_label": LEVELS[sess["level"]],
        "level_rules": rules,
        "status": sess["status"],
        "symptom": chain["symptom"],
        "visible": visible,
        "confirmed_path": confirmed_path,
        "pruned": pruned,
        "tests_done": sess["tests_done"],
        "hints_used": sess["hints_used"],
        "misdiagnoses": sess["misdiagnoses"],
        "roots_found": len(sess["confirmed_roots"]),
        "roots_required": len(sess["required_roots"]),
        "time_limit_sec": sess.get("time_limit_sec"),
        "remaining_sec": remaining,
        "morph_events": sess["morph_events"],
        "suggestion": sess.get("suggestion"),
        "score": sess.get("score"),
        "verdict": sess.get("verdict"),
        "started_at": sess["started_at"],
    }


def start_session(student_no: str, student_name: str, domain: str, level: int = 0) -> dict:
    """开局：注入故障表象，展开第一层原因分支。level=0 表示使用学生当前等级"""
    chain = _get_chain(domain)
    if not chain:
        return {"ok": False, "error": f"未知故障域: {domain}"}
    student_no = str(student_no or "").strip()
    if not student_no:
        return {"ok": False, "error": "学号不能为空"}

    data = _load()
    # 已有进行中的同域会话则直接返回（幂等）
    for s in data["sessions"].values():
        if (s.get("student_no") == student_no and s.get("domain") == domain
                and s.get("status") == "active"):
            return {"ok": True, "resumed": True, "session": _session_public(s)}

    if not level:
        level = int(data.get("levels", {}).get(student_no, {}).get(domain, 1))
    level = max(1, min(3, int(level)))
    rules = _level_rules(level)

    l1_nodes = [nid for nid, n in chain["nodes"].items()
                if n.get("parent") == "symptom" and not n.get("expert_only")]

    required_roots = []
    for nid, n in chain["nodes"].items():
        if n.get("root") and not n.get("expert_only"):
            required_roots.append(nid)
    if rules.get("multi_fault") and chain.get("secondary_root"):
        required_roots.append(chain["secondary_root"])

    time_limit = rules.get("time_limit")
    deadline = None
    if time_limit:
        deadline = (datetime.now() + timedelta(seconds=time_limit)).strftime("%Y-%m-%d %H:%M:%S")

    sess = {
        "session_id": "fc_" + uuid.uuid4().hex[:10],
        "student_no": student_no,
        "student_name": student_name or "",
        "domain": domain,
        "level": level,
        "status": "active",
        "started_at": _now(),
        "finished_at": "",
        "depth": 0,
        "revealed": list(l1_nodes),
        "pruned": [],
        "confirmed_path": [],
        "confirmed_roots": [],
        "required_roots": required_roots,
        "tests_done": [],
        "hints_used": 0,
        "misdiagnoses": 0,
        "time_limit_sec": time_limit,
        "deadline": deadline,
        "timed_out": False,
        "morph_events": [],
        "suggestion": None,
        "score": None,
        "verdict": None,
    }
    data["sessions"][sess["session_id"]] = sess
    _save(data)
    return {"ok": True, "session": _session_public(sess)}


def _check_timeout(sess: dict):
    """专家级倒计时检查"""
    if sess.get("deadline") and sess["status"] == "active":
        if datetime.now() > datetime.strptime(sess["deadline"], "%Y-%m-%d %H:%M:%S"):
            sess["timed_out"] = True


def perform_test(student_no: str, session_id: str, test_id: str) -> dict:
    """执行测试动作：确认分支（展开下一层）或剪除分支。专家级干扰测试只返回含糊结果"""
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] != "active":
        return {"ok": False, "error": "会话已结束"}
    _check_timeout(sess)

    chain = _get_chain(sess["domain"])
    rules = _level_rules(sess["level"])

    # 专家级干扰测试：结果含糊，不改变状态
    for nid, node in chain["nodes"].items():
        d = node.get("decoy_test")
        if d and d["id"] == test_id:
            if not rules.get("decoys"):
                return {"ok": False, "error": "该测试在当前难度不可用"}
            sess["tests_done"].append({"test_id": test_id, "node_id": nid,
                                       "name": d["name"], "result": "noise",
                                       "text": d["result_text"], "ts": _now()})
            _save(data)
            return {"ok": True, "result": "noise", "text": d["result_text"],
                    "session": _session_public(sess)}

    # 正常鉴别测试
    target_node, target_nid = None, None
    for nid, node in chain["nodes"].items():
        if node.get("test") and node["test"]["id"] == test_id:
            target_node, target_nid = node, nid
            break
    if not target_node:
        return {"ok": False, "error": "未知测试动作"}
    if target_nid not in _visible_nodes(sess):
        return {"ok": False, "error": "该分支当前不可测试（未展开或已剪除）"}

    t = target_node["test"]
    has_children = bool(t.get("confirm_expands")) or bool(t.get("expert_expands"))
    is_on_real_path = has_children

    # 专家级多故障：secondary_entry 分支在专家级转为确认（并发第二根因路径）
    expert_confirm = (rules.get("multi_fault") and t.get("expert_expands")
                      and sess["domain"] and chain.get("secondary_entry") == target_nid)

    result, text = "reject", t.get("reject_text", "测试排除了该分支")
    if expert_confirm:
        result, text = "confirm", t.get("expert_confirm_text", "")
        expands = t.get("expert_expands", [])
    elif is_on_real_path:
        result, text = "confirm", t.get("confirm_text", "")
        expands = t.get("confirm_expands", [])
    else:
        expands = []

    sess["tests_done"].append({"test_id": test_id, "node_id": target_nid,
                               "name": t["name"], "result": result,
                               "text": text, "ts": _now()})

    newly_revealed = []
    if result == "confirm":
        sess["depth"] = sess.get("depth", 0) + 1
        if target_nid not in sess["confirmed_path"]:
            sess["confirmed_path"].append(target_nid)
        for cid in expands:
            cnode = chain["nodes"].get(cid)
            if not cnode:
                continue
            if cnode.get("expert_only") and sess["level"] < 3:
                continue
            if cid not in sess["revealed"]:
                sess["revealed"].append(cid)
                newly_revealed.append(cid)
        # 直接确认出根因节点时纳入已发现根因
        for cid in expands:
            cnode = chain["nodes"].get(cid, {})
            if cnode.get("root") and cid not in sess["confirmed_roots"] \
                    and cid in sess["required_roots"]:
                # 根因节点仍需学生显式提交诊断，这里只展开
                pass
        # 高效剪枝检测：连续两次测试均为 confirm 且未走弯路 → 专家方向变形
        recent = sess["tests_done"][-2:]
        if (len(recent) == 2 and all(r["result"] == "confirm" for r in recent)
                and sess["level"] == 3 and rules.get("decoys")):
            # 即时注入干扰变量提示（动态变形事件）
            event = {"type": "inject_noise", "ts": _now(),
                     "text": "⚡ 动态变形：你的排查效率很高，现场出现新的干扰信息，注意甄别"}
            if not any(e.get("type") == "inject_noise" for e in sess["morph_events"]):
                sess["morph_events"].append(event)
    else:
        if target_nid not in sess["pruned"]:
            sess["pruned"].append(target_nid)

    _save(data)
    return {"ok": True, "result": result, "text": text,
            "newly_revealed": [_node_public(sess, nid) for nid in newly_revealed],
            "session": _session_public(sess)}


def use_hint(student_no: str, session_id: str) -> dict:
    """使用提示（入门免费展示分支提示；工程师级调用此接口扣分；专家级禁用）"""
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] != "active":
        return {"ok": False, "error": "会话已结束"}
    rules = _level_rules(sess["level"])
    if not rules.get("hints"):
        return {"ok": False, "error": "专家难度禁用提示"}
    chain = _get_chain(sess["domain"])
    visible = _visible_nodes(sess)
    hints = []
    for nid in visible:
        node = chain["nodes"].get(nid, {})
        if node.get("hint"):
            hints.append({"node_id": nid, "label": node["label"], "hint": node["hint"]})
    if sess["level"] == 2:
        sess["hints_used"] += 1  # 工程师级才扣分；入门级分支提示本就免费展示
    _save(data)
    return {"ok": True, "hints": hints, "hints_used": sess["hints_used"],
            "penalty_each": PENALTY_HINT if sess["level"] == 2 else 0,
            "session": _session_public(sess)}


def _evaluate_morph(sess: dict, data: dict) -> list:
    """诊断后评估难度变形：返回等级变化建议（下局生效），并持久化"""
    events = []
    student_no = sess["student_no"]
    domain = sess["domain"]
    cur = int(data.get("levels", {}).get(student_no, {}).get(domain, 1))

    if sess["misdiagnoses"] >= 2 and cur > 1:
        stu = data.setdefault("levels", {}).setdefault(student_no, {})
        stu[domain] = cur - 1
        sess["suggestion"] = {
            "type": "downgrade",
            "text": f"连续误诊 {sess['misdiagnoses']} 次，已为你把「{DOMAIN_LABELS[domain]}」难度从 {LEVELS[cur]} 调整为 {LEVELS[cur-1]}，下局生效",
            "before": cur, "after": cur - 1,
        }
        sess["morph_events"].append({"type": "downgrade", "ts": _now(),
                                     "before": cur, "after": cur - 1})
        events.append(sess["suggestion"])
    elif sess["misdiagnoses"] == 0 and sess["score"] is not None and sess["score"] >= 80 and cur < 3:
        stu = data.setdefault("levels", {}).setdefault(student_no, {})
        stu[domain] = cur + 1
        sess["suggestion"] = {
            "type": "upgrade",
            "text": f"零误诊且得分 {sess['score']}，「{DOMAIN_LABELS[domain]}」难度从 {LEVELS[cur]} 升级为 {LEVELS[cur+1]}，下局解锁更多挑战",
            "before": cur, "after": cur + 1,
        }
        sess["morph_events"].append({"type": "upgrade", "ts": _now(),
                                     "before": cur, "after": cur + 1})
        events.append(sess["suggestion"])
    return events


def diagnose(student_no: str, session_id: str, root_ids: list, fix_ids: list) -> dict:
    """提交根因诊断 + 处置方案，输出评分与难度变形结果"""
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] != "active":
        return {"ok": False, "error": "会话已结束"}
    _check_timeout(sess)

    chain = _get_chain(sess["domain"])
    required = set(sess["required_roots"])
    chosen = set(root_ids or [])
    fixes = set(fix_ids or [])

    correct_roots = required & chosen
    wrong_roots = chosen - required
    missed = required - chosen

    # 收集正确处置
    right_fixes, all_fixes = set(), {}
    for rid in required:
        node = chain["nodes"].get(rid, {})
        if node.get("root"):
            for f in node["root"]["fixes"]:
                all_fixes[f["id"]] = f
                if f.get("ok"):
                    right_fixes.add(f["id"])
    chosen_right_fixes = fixes & right_fixes

    is_full_correct = (not missed) and (not wrong_roots)

    # ---- 评分 ----
    n_required = max(1, len(required))
    root_score = round(SCORE_ROOT * len(correct_roots) / n_required)
    if wrong_roots:
        root_score = max(0, root_score - SCORE_ROOT // 2 * len(wrong_roots))

    fix_score = round(SCORE_FIX * len(chosen_right_fixes) / max(1, len(right_fixes)))
    wrong_fixes = fixes - right_fixes
    if wrong_fixes:
        fix_score = max(0, fix_score - 7 * len(wrong_fixes))

    par = chain.get("par", {}).get(sess["level"], 3)
    actual_tests = len([t for t in sess["tests_done"] if t["result"] != "noise"])
    if sess["timed_out"]:
        eff_score = 0
    else:
        eff_score = round(SCORE_EFFICIENCY * min(1.0, par / max(1, actual_tests)))

    bonus = SCORE_NO_MISDIAG if sess["misdiagnoses"] == 0 and is_full_correct else 0

    # 误诊：本次诊断不完全正确计一次误诊
    if not is_full_correct:
        sess["misdiagnoses"] += 1

    score = root_score + fix_score + eff_score + bonus
    score -= PENALTY_MISDIAG * sess["misdiagnoses"]
    if sess["level"] == 2:
        score -= PENALTY_HINT * sess["hints_used"]
    if sess["timed_out"]:
        score -= PENALTY_TIMEOUT
    score = max(0, min(100, score))
    sess["score"] = score

    grade = "S" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"

    # 根因详情（诊断后揭示）
    reveal = []
    for rid in sess["required_roots"]:
        node = chain["nodes"].get(rid, {})
        if node.get("root"):
            reveal.append({
                "id": rid, "label": node["label"],
                "cause": node["root"]["cause"],
                "found": rid in correct_roots,
                "fixes": node["root"]["fixes"],
            })

    sess["verdict"] = {
        "full_correct": is_full_correct,
        "correct_roots": sorted(correct_roots),
        "wrong_roots": sorted(wrong_roots),
        "missed_roots": sorted(missed),
        "root_score": root_score,
        "fix_score": fix_score,
        "eff_score": eff_score,
        "bonus": bonus,
        "par_tests": par,
        "actual_tests": actual_tests,
        "timed_out": sess["timed_out"],
        "grade": grade,
        "reveal": reveal,
    }

    if is_full_correct or sess["misdiagnoses"] >= 3 or sess["timed_out"]:
        # 结束会话：完全诊断成功，或误诊 3 次熔断，或超时
        sess["status"] = "done"
        sess["finished_at"] = _now()
        morph = _evaluate_morph(sess, data)
        data["history"].append({
            "session_id": sess["session_id"], "student_no": sess["student_no"],
            "student_name": sess.get("student_name", ""), "domain": sess["domain"],
            "level": sess["level"], "score": score, "grade": grade,
            "full_correct": is_full_correct, "misdiagnoses": sess["misdiagnoses"],
            "tests": actual_tests, "par": par, "hints_used": sess["hints_used"],
            "timed_out": sess["timed_out"], "finished_at": sess["finished_at"],
            "morph": morph[0]["type"] if morph else "",
        })
        data["history"] = data["history"][-200:]
    else:
        sess["verdict"]["continue"] = True

    _save(data)
    return {"ok": True, "score": score, "grade": grade, "verdict": sess["verdict"],
            "session": _session_public(sess)}


def get_session(student_no: str, session_id: str) -> dict:
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    _check_timeout(sess)
    _save(data)
    return {"ok": True, "session": _session_public(sess)}


def abandon_session(student_no: str, session_id: str) -> dict:
    """放弃当前会话（允许重开）"""
    data = _load()
    sess = data["sessions"].get(session_id)
    if not sess or sess.get("student_no") != str(student_no):
        return {"ok": False, "error": "会话不存在或无权操作"}
    if sess["status"] == "active":
        sess["status"] = "done"
        sess["finished_at"] = _now()
        sess["verdict"] = {"abandoned": True}
        data["history"].append({
            "session_id": sess["session_id"], "student_no": sess["student_no"],
            "student_name": sess.get("student_name", ""), "domain": sess["domain"],
            "level": sess["level"], "score": 0, "grade": "-", "full_correct": False,
            "misdiagnoses": sess["misdiagnoses"], "tests": len(sess["tests_done"]),
            "par": 0, "hints_used": sess["hints_used"], "timed_out": False,
            "finished_at": sess["finished_at"], "morph": "abandoned",
        })
        _save(data)
    return {"ok": True}


def get_history(student_no: str = "", limit: int = 50) -> list:
    """历史成绩（教师可查看全部）"""
    data = _load()
    hist = data.get("history", [])
    if student_no:
        hist = [h for h in hist if h.get("student_no") == str(student_no)]
    return list(reversed(hist[-limit:]))


def stats_overview() -> dict:
    """教师看板：整体概览"""
    data = _load()
    hist = data.get("history", [])
    done = [h for h in hist if h.get("morph") != "abandoned"]
    avg = round(sum(h.get("score", 0) for h in done) / len(done), 1) if done else 0
    by_domain = {}
    for h in done:
        d = h.get("domain", "")
        by_domain.setdefault(d, {"count": 0, "total": 0})
        by_domain[d]["count"] += 1
        by_domain[d]["total"] += h.get("score", 0)
    domain_stats = [{"domain": d, "label": DOMAIN_LABELS.get(d, d),
                     "count": v["count"], "avg": round(v["total"] / v["count"], 1)}
                    for d, v in by_domain.items()]
    morph_up = len([h for h in done if h.get("morph") == "upgrade"])
    morph_down = len([h for h in done if h.get("morph") == "downgrade"])
    return {
        "total_sessions": len(hist),
        "completed": len(done),
        "avg_score": avg,
        "upgrades": morph_up,
        "downgrades": morph_down,
        "domain_stats": domain_stats,
        "active_sessions": len([s for s in data.get("sessions", {}).values()
                                if s.get("status") == "active"]),
    }


def build_tutor_context(sess: dict) -> str:
    """组装给 AI 导师的上下文（ground 在当前链状态，不泄露根因答案）"""
    chain = _get_chain(sess["domain"])
    rules = _level_rules(sess["level"])
    lines = [
        f"当前故障场景：{chain['title']}（{chain['domain_label']}，难度：{LEVELS[sess['level']]}）",
        f"故障表象：{chain['symptom']['alarm']}；{chain['symptom']['scene']}",
        f"已知信息：{chain['symptom']['known']}",
    ]
    if sess["confirmed_path"]:
        labels = [chain["nodes"][nid]["label"] for nid in sess["confirmed_path"] if nid in chain["nodes"]]
        lines.append("学生已确认的原因分支：" + " → ".join(labels))
    if sess["pruned"]:
        labels = [chain["nodes"][nid]["label"] for nid in sess["pruned"] if nid in chain["nodes"]]
        lines.append("学生已排除的分支：" + "、".join(labels))
    if sess["tests_done"]:
        last = sess["tests_done"][-1]
        lines.append(f"最近一次测试：{last['name']}，结果：{last['text']}")
    lines.append(f"已做测试 {len(sess['tests_done'])} 次，误诊 {sess['misdiagnoses']} 次，用提示 {sess['hints_used']} 次。")
    lines.append("你是现场资深带教导师，用苏格拉底式提问引导学生自己推理，"
                 "绝对不要直接说出根因或处置答案；可以讲解排查方法论、仪表使用、"
                 "告警含义。回答简短，像师傅带徒弟，3~6 句话。")
    if not rules.get("hints"):
        lines.append("当前为专家难度：学生禁用提示，你也不要给方向性提示，只纠正方法论错误。")
    return "\n".join(lines)


def get_session_raw(session_id: str) -> dict:
    """内部用：取原始会话（导师上下文用）"""
    data = _load()
    return data.get("sessions", {}).get(session_id)
