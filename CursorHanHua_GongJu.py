# -*- coding: utf-8 -*-
"""
Cursor 汉化 + 用量监控工具
功能：
  1. 将翻译脚本注入 Cursor 的 workbench.html，实现设置页面中文化
  2. 自动从本地数据库读取认证令牌，调用 API 获取用量数据
  3. 在 Cursor 设置页面用户信息区域下方显示实时用量情况

用法：
  python CursorHanHua_GongJu.py --apply     汉化 + 用量显示
  python CursorHanHua_GongJu.py --restore   恢复原始文件
"""

import os  # 文件路径操作
import sys  # 系统参数
import shutil  # 文件复制
import datetime  # 时间戳
import hashlib  # 哈希计算
import base64  # Base64 编码
import json  # JSON 读写
import sqlite3  # SQLite 数据库
import urllib.request  # HTTP 请求
import urllib.error  # HTTP 错误处理
import platform  # 平台识别

# ============================================================
# ★★★ 用户配置区域 ★★★
# ============================================================

# 当前平台
DANG_QIAN_XI_TONG = platform.system().lower()

# Cursor 安装根目录
if DANG_QIAN_XI_TONG == 'windows':
    CURSOR_AN_ZHUANG_LU_JING = r"D:\Tools\cursor"
elif DANG_QIAN_XI_TONG == 'linux':
    CURSOR_AN_ZHUANG_LU_JING = "/usr/share/cursor"
else:
    CURSOR_AN_ZHUANG_LU_JING = "/usr/share/cursor"

# Cursor 用户数据目录（存放认证令牌等）
# 如果使用 --user-data-dir 自定义了目录，请改为对应路径
if DANG_QIAN_XI_TONG == 'windows':
    CURSOR_SHU_JU_LU_JING = r"D:\Tools\cursor\user"
elif DANG_QIAN_XI_TONG == 'linux':
    CURSOR_SHU_JU_LU_JING = os.path.expanduser("~/.cursor")
else:
    CURSOR_SHU_JU_LU_JING = os.path.expanduser("~/.cursor")

# 以下路径一般不需要修改
GONG_ZUO_TAI_HTML_XIANG_DUI = os.path.join("resources", "app", "out", "vs", "code", "electron-sandbox", "workbench")  # workbench 目录相对路径
GONG_ZUO_TAI_HTML_MING = "workbench.html"  # workbench HTML 文件名
HAN_HUA_JS_MING = "cursor_hanhua.js"  # 翻译脚本文件名
FAN_YI_CI_DIAN_MING = "cursor_fanyi_dic.txt"  # 翻译词典文本文件名
ZHU_RU_BIAO_JI = "<!-- CURSOR_HANHUA_INJECTION -->"  # 注入标记
BEI_FEN_HOU_ZHUI = ".bak"  # 备份文件后缀

# API 端点
API_YONG_LIANG = "https://api2.cursor.sh/auth/usage"  # 高级请求用量
API_YONG_LIANG_ZONG_JIE = "https://www.cursor.com/api/usage-summary"  # 总用量摘要
API_GE_REN_XIN_XI = "https://api2.cursor.sh/auth/full_stripe_profile"  # 个人信息

# state.vscdb 中的认证键名
DB_XIANG_DUI_LU_JING = os.path.join("User", "globalStorage", "state.vscdb")  # 数据库相对路径
LING_PAI_JIAN_MING = "cursorAuth/accessToken"  # 访问令牌键名
YOU_XIANG_JIAN_MING = "cursorAuth/cachedEmail"  # 邮箱键名


# ============================================================
# ★★★ 认证与 API 函数 ★★★
# ============================================================

def DuQu_FangWen_LingPai():
    """从 Cursor 本地 state.vscdb 数据库读取访问令牌和用户邮箱"""
    ShuJuKu_LuJing = os.path.join(CURSOR_SHU_JU_LU_JING, DB_XIANG_DUI_LU_JING)  # 数据库完整路径
    if not os.path.exists(ShuJuKu_LuJing):  # 检查数据库是否存在
        print(f"[警告] 未找到 Cursor 数据库: {ShuJuKu_LuJing}")
        return None, None

    try:
        LianJie = sqlite3.connect(ShuJuKu_LuJing)  # 连接数据库
        YouBiao = LianJie.cursor()  # 创建游标

        YouBiao.execute("SELECT value FROM ItemTable WHERE key=?", (LING_PAI_JIAN_MING,))  # 查询访问令牌
        JieGuo = YouBiao.fetchone()  # 获取结果
        LingPai = JieGuo[0] if JieGuo else None  # 提取令牌值

        YouBiao.execute("SELECT value FROM ItemTable WHERE key=?", (YOU_XIANG_JIAN_MING,))  # 查询邮箱
        JieGuo = YouBiao.fetchone()  # 获取结果
        YouXiang = JieGuo[0] if JieGuo else None  # 提取邮箱值

        LianJie.close()  # 关闭数据库连接
        return LingPai, YouXiang  # 返回令牌和邮箱
    except Exception as CuoWu:
        print(f"[警告] 读取数据库失败: {CuoWu}")
        return None, None


def GouZao_Cookie(LingPai):
    """从访问令牌构造 WorkosCursorSessionToken Cookie"""
    try:
        BuFen = LingPai.split('.')  # JWT 由三部分组成
        if len(BuFen) >= 2:  # 至少需要 header 和 payload
            TianChong = BuFen[1] + '=' * (4 - len(BuFen[1]) % 4)  # 补齐 Base64 填充
            JieXi = json.loads(base64.b64decode(TianChong).decode('utf-8'))  # 解码 payload
            YongHu_Id = JieXi.get('sub', '').replace('auth0|', '')  # 提取用户 ID
            return f"{YongHu_Id}::{LingPai}"  # 组合为 Cookie 格式
    except Exception:
        pass
    return None


def HuoQu_YongLiang_ZongJie(LingPai):
    """调用 cursor.com/api/usage-summary 获取总用量摘要"""
    Cookie_Zhi = GouZao_Cookie(LingPai)  # 构造 Cookie
    if not Cookie_Zhi:  # Cookie 构造失败
        return None

    try:
        QingQiu = urllib.request.Request(API_YONG_LIANG_ZONG_JIE)  # 创建请求
        QingQiu.add_header('Cookie', f'WorkosCursorSessionToken={Cookie_Zhi}')  # 添加认证 Cookie
        QingQiu.add_header('Accept', 'application/json')  # 期望 JSON 响应
        XiangYing = urllib.request.urlopen(QingQiu, timeout=10)  # 发送请求
        return json.loads(XiangYing.read().decode('utf-8'))  # 解析 JSON 响应
    except Exception as CuoWu:
        print(f"[警告] 获取总用量摘要失败: {CuoWu}")
        return None


def HuoQu_GaoJi_YongLiang(LingPai):
    """调用 api2.cursor.sh/auth/usage 获取高级请求用量"""
    try:
        QingQiu = urllib.request.Request(API_YONG_LIANG)  # 创建请求
        QingQiu.add_header('Authorization', f'Bearer {LingPai}')  # Bearer 令牌认证
        QingQiu.add_header('Accept', 'application/json')  # 期望 JSON 响应
        XiangYing = urllib.request.urlopen(QingQiu, timeout=10)  # 发送请求
        return json.loads(XiangYing.read().decode('utf-8'))  # 解析 JSON 响应
    except Exception as CuoWu:
        print(f"[警告] 获取高级请求用量失败: {CuoWu}")
        return None


def ZhengHe_YongLiang_ShuJu(LingPai):
    """整合所有用量数据为统一格式"""
    ShuJu = {  # 默认数据结构
        "zongYong": 0,       # 总使用次数
        "zongXian": 2000,    # 总限额（PRO 默认 2000）
        "shengYu": 2000,     # 剩余次数
        "gaoJiYong": 0,      # 高级请求使用次数
        "gaoJiXian": 500,    # 高级请求限额（PRO 默认 500）
        "zongBaiFen": 0,     # 总使用百分比
        "apiBaiFen": 0,      # API 使用百分比
        "jiFeiKaiShi": "",   # 计费周期开始
        "jiFeiJieShu": "",   # 计费周期结束
        "gengXinShiJian": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # 数据更新时间
        "jiHua": "pro",      # 计划类型
        "youXiao": False,    # 数据是否有效
        "moXingXiangQing": {}  # 各模型详细用量
    }

    # 获取总用量摘要
    ZongJie = HuoQu_YongLiang_ZongJie(LingPai)  # 调用 API
    if ZongJie and 'individualUsage' in ZongJie:  # 有有效数据
        JiHua = ZongJie['individualUsage'].get('plan', {})  # 提取计划用量
        ShuJu["zongYong"] = JiHua.get('used', 0)  # 已使用次数
        ShuJu["zongXian"] = JiHua.get('limit', 2000)  # 总限额
        ShuJu["shengYu"] = JiHua.get('remaining', 0)  # 剩余次数
        ShuJu["zongBaiFen"] = round(JiHua.get('totalPercentUsed', 0), 1)  # 总百分比
        ShuJu["apiBaiFen"] = round(JiHua.get('apiPercentUsed', 0), 1)  # API 百分比
        ShuJu["jiHua"] = ZongJie.get('membershipType', 'pro')  # 计划类型
        ShuJu["youXiao"] = True  # 标记为有效

        # 解析计费周期日期
        KaiShi = ZongJie.get('billingCycleStart', '')  # 开始日期
        JieShu = ZongJie.get('billingCycleEnd', '')  # 结束日期
        if KaiShi:
            ShuJu["jiFeiKaiShi"] = KaiShi[:10]  # 只取日期部分
        if JieShu:
            ShuJu["jiFeiJieShu"] = JieShu[:10]  # 只取日期部分

    # 获取高级请求用量（含各模型详细数据）
    GaoJi = HuoQu_GaoJi_YongLiang(LingPai)  # 调用 API
    if GaoJi:
        MoXing_ShuJu = {}  # 模型详情字典
        for JianMing in GaoJi:
            if JianMing == 'startOfMonth':  # 跳过非模型键
                continue
            MoXing_XinXi = GaoJi[JianMing]  # 提取模型数据
            MoXing_ShuJu[JianMing] = {
                "qingQiu": MoXing_XinXi.get('numRequests', 0),       # 请求数
                "shangXian": MoXing_XinXi.get('maxRequestUsage', 0),  # 请求上限
                "lingPaiShu": MoXing_XinXi.get('numTokens', 0)       # Token 数
            }
        ShuJu["moXingXiangQing"] = MoXing_ShuJu  # 存入模型详情
        # 总用量 zongYong 保持来自 usage-summary 的 plan.used，不在此覆盖

        if 'gpt-4' in GaoJi:  # 有 gpt-4 类别数据
            ShuJu["gaoJiYong"] = GaoJi['gpt-4'].get('numRequests', 0)
            ShuJu["gaoJiXian"] = GaoJi['gpt-4'].get('maxRequestUsage', 500)

        # 从 startOfMonth 补充计费周期（兜底，当 usage-summary 未取到时）
        if not ShuJu["jiFeiJieShu"] and 'startOfMonth' in GaoJi:
            try:
                KaiShiRi = datetime.datetime.fromisoformat(GaoJi['startOfMonth'].replace('Z', '+00:00'))
                ShuJu["jiFeiKaiShi"] = KaiShiRi.strftime('%Y-%m-%d')
                Nian = KaiShiRi.year + (KaiShiRi.month // 12)
                Yue = (KaiShiRi.month % 12) + 1
                JieShuRi = KaiShiRi.replace(year=Nian, month=Yue)
                ShuJu["jiFeiJieShu"] = JieShuRi.strftime('%Y-%m-%d')
            except Exception:
                pass

        if not ShuJu["youXiao"]:
            ShuJu["youXiao"] = True

    return ShuJu  # 返回整合后的数据


def HuoQu_FanYi_CiDian_LuJing():
    """获取翻译词典文本文件路径"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), FAN_YI_CI_DIAN_MING)


def JieXi_FanYi_CiTiao(Hang, HangHao):
    """解析单行翻译词条"""
    FenGeFu = Hang.find('=>')
    if FenGeFu == -1:
        raise ValueError(f"第 {HangHao} 行缺少 => 分隔符")
    
    # Hang 是当前行文本，HangHao 是行号
    FenGeFu = Hang.find('=>')

    # 1. 检查是否有 => 分隔符
    if FenGeFu == -1:
        raise ValueError(f"第 {HangHao} 行缺少 => 分隔符")

    # 2. 按 => 分割成两段
    translateConfig = Hang.split('=>', 1)  # 只分割第一次出现的 =>

    # 3. 取出原文和译文，并 trim 去空格
    YuanWen = translateConfig[0].strip()
    YiWen = translateConfig[1].strip()

    # 4. 如果原文被 "" 包裹，就去掉前后的 "
    if YuanWen.startswith('"') and YuanWen.endswith('"'):
        YuanWen = YuanWen[1:-1]

    # 5. 如果译文被 "" 包裹，就去掉前后的 "
    if YiWen.startswith('"') and YiWen.endswith('"'):
        YiWen = YiWen[1:-1]


    if not YuanWen or not YiWen:
        raise ValueError(f"第 {HangHao} 行键或值为空")


    # try:
    #     Jian = json.loads(YuanWen)
    #     Zhi = json.loads(YiWen)
    # except Exception as CuoWu:
    #     raise ValueError(f"第 {HangHao} 行解析失败: {CuoWu}") from CuoWu

    print(f"载入翻译 原文: {YuanWen} 翻译: {YiWen}")

    return YuanWen, YiWen


def DuQu_FanYi_CiDian():
    """从外部文本文件读取翻译词典"""
    LuJing_CiDian = HuoQu_FanYi_CiDian_LuJing()
    if not os.path.exists(LuJing_CiDian):
        print(f"[错误] 未找到翻译词典文件: {LuJing_CiDian}")
        sys.exit(1)

    ShuJu = {}
    try:
        with open(LuJing_CiDian, 'r', encoding='utf-8') as WenJian:
            for HangHao, Hang in enumerate(WenJian, start=1):
                QuKong = Hang.strip()
                if not QuKong:
                    continue
                if QuKong.startswith('#') or QuKong.startswith('//'):
                    continue

                Jian, Zhi = JieXi_FanYi_CiTiao(QuKong, HangHao)
                ShuJu[Jian] = Zhi
    except Exception as CuoWu:
        print(f"[错误] 读取翻译词典失败: {CuoWu}")
        sys.exit(1)

    return ShuJu


# ============================================================
# ★★★ JavaScript 代码生成 ★★★
# ============================================================

def ShengCheng_JS_DaiMa(YongLiang_ShuJu, FanYi_CiDian_ShuJu, YuanShi_LingPai=""):
    """生成包含翻译、用量显示和实时刷新的完整 JavaScript 代码"""

    # 将用量数据序列化为 JSON
    YongLiang_Json = json.dumps(YongLiang_ShuJu, ensure_ascii=False)  # 用量 JSON 字符串
    FanYi_CiDian_Json = json.dumps(FanYi_CiDian_ShuJu, ensure_ascii=False)  # 翻译词典 JSON 字符串

    # 将令牌 Base64 编码后嵌入（基础保护，防止明文出现）
    BianMa_LingPai_Str = ""
    if YuanShi_LingPai:
        BianMa_LingPai_Str = base64.b64encode(YuanShi_LingPai.encode('utf-8')).decode('utf-8')

    return '''\
/*
 * Cursor 汉化 + 用量监控脚本
 * Auto-generated by CursorHanHua_GongJu.py
 * Generated: ''' + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '''
 */
(function() {
    'use strict';

    // ================================================================
    // SECTION 1: 翻译字典
    // ================================================================

    var FanYi_CiDian = new Map(Object.entries(''' + FanYi_CiDian_Json + '''));
    var MoShi_FanYi = [
        [/^(\\d+) requests? remaining$/i, "$1 次请求剩余"],
        [/^(\\d+) of (\\d+) requests?$/i, "$1 / $2 次请求"],
        [/^(\\d+) premium requests?$/i, "$1 次高级请求"],
        [/^(\\d+) files? indexed$/i, "$1 个文件已索引"],
        [/^Indexing (\\d+) files?$/i, "正在索引 $1 个文件"],
        [/^(\\d+) errors?$/i, "$1 个错误"],
        [/^(\\d+) warnings?$/i, "$1 个警告"],
        [/^Version (.+)$/i, "版本 $1"],
        [/^(\\d+) tools?$/i, "$1 个工具"],
        [/^(\\d+) resources?$/i, "$1 个资源"],
        [/^(\\d+) prompts?$/i, "$1 个提示词"],
        [/^Updated (.+) ago$/i, "$1前更新"],
        [/^(\\d+) seconds? ago$/i, "$1 秒前"],
        [/^(\\d+) minutes? ago$/i, "$1 分钟前"],
        [/^(\\d+) hours? ago$/i, "$1 小时前"],
        [/^(\\d+) days? ago$/i, "$1 天前"],
        [/^Auto-Run Mode Disabled by Team Admin$/i, "自动运行模式已被团队管理员禁用"],
        [/^Auto-Run Mode Controlled by Team Admin$/i, "自动运行模式由团队管理员控制"],
        [/^Auto-Run Mode Controlled by Team Admin \\(Sandbox Enabled\\)$/i, "自动运行模式由团队管理员控制（沙盒已启用）"],
        [/^Custom cron: (.+)$/i, "自定义 Cron：$1"],
        [/^(.+) at (.+)$/i, "$1 于 $2"],
        [/^Automatically index any new folders with fewer than (\\d+) files$/i, "自动索引文件数少于 $1 的新文件夹"],
        [/^(\\d+) hooks?$/i, "$1 个钩子"],
        [/^(\\d+) automations?$/i, "$1 个自动化"],
        [/^(\\d+) rules?$/i, "$1 条规则"],
        [/^(\\d+) skills?$/i, "$1 个技能"],
        [/^(\\d+) commands?$/i, "$1 个命令"],
        [/^(\\d+) subagents?$/i, "$1 个子智能体"]
    ];

    // ================================================================
    // SECTION 2: 翻译引擎
    // ================================================================

    var TiaoGuo_XuanZeQi = '.monaco-editor, .overflow-guard, .view-lines, .editor-scrollable, .inputarea, .rename-input';
    var TiaoGuo_BiaoQian = new Set(['TEXTAREA', 'INPUT', 'SCRIPT', 'STYLE', 'CODE', 'PRE', 'NOSCRIPT']);

    function FanYi_WenBen_JieDian(node) {
        var text = node.textContent;
        if (!text) return;
        var trimmed = text.trim();
        if (!trimmed || trimmed.length > 500) return;
        if (/^[\\d\\s.,;:!?@#$%^&*()\\-+=<>\\/\\\\|~`'"[\\]{}]+$/.test(trimmed)) return;
        if (/[\\u4e00-\\u9fff]/.test(trimmed) && (trimmed.match(/[\\u4e00-\\u9fff]/g) || []).length > trimmed.length * 0.3) return;

        if (FanYi_CiDian.has(trimmed)) {
            var prefix = text.substring(0, text.indexOf(trimmed));
            var suffix = text.substring(text.indexOf(trimmed) + trimmed.length);
            node.textContent = prefix + FanYi_CiDian.get(trimmed) + suffix;
            return;
        }

        for (var i = 0; i < MoShi_FanYi.length; i++) {
            var pair = MoShi_FanYi[i];
            if (pair[0].test(trimmed)) {
                var result = trimmed.replace(pair[0], pair[1]);
                node.textContent = text.replace(trimmed, result);
                return;
            }
        }
    }

    function FanYi_ShuXing(el) {
        var attrs = ['title', 'aria-label', 'placeholder'];
        for (var i = 0; i < attrs.length; i++) {
            var val = el.getAttribute(attrs[i]);
            if (val) {
                var trimmed = val.trim();
                if (FanYi_CiDian.has(trimmed)) {
                    el.setAttribute(attrs[i], FanYi_CiDian.get(trimmed));
                }
            }
        }
    }

    function Shi_BianJiQi_QuYu(node) {
        var el = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        if (!el) return true;
        if (TiaoGuo_BiaoQian.has(el.tagName)) return true;
        try { if (el.closest(TiaoGuo_XuanZeQi)) return true; } catch (e) {}
        return false;
    }

    function FanYi_ZiShu(root) {
        var stack = [root];
        while (stack.length > 0) {
            var node = stack.pop();
            if (node.nodeType === Node.ELEMENT_NODE) {
                if (TiaoGuo_BiaoQian.has(node.tagName)) continue;
                if (node.classList && (node.classList.contains('monaco-editor') || node.classList.contains('overflow-guard') || node.classList.contains('view-lines') || node.classList.contains('editor-scrollable'))) continue;
                if (node.getAttribute('contenteditable') === 'true') continue;
                if (node.id === 'cursor-yongliang-xianshi') continue;
                FanYi_ShuXing(node);
                var children = node.childNodes;
                for (var i = children.length - 1; i >= 0; i--) { stack.push(children[i]); }
            } else if (node.nodeType === Node.TEXT_NODE) {
                if (!Shi_BianJiQi_QuYu(node)) { FanYi_WenBen_JieDian(node); }
            }
        }
    }

    var DaiChuLi_JieDian = [];
    var YiDiaoDu = false;

    function TianJia_DaiChuLi(node) {
        DaiChuLi_JieDian.push(node);
        if (!YiDiaoDu) {
            YiDiaoDu = true;
            requestAnimationFrame(ZhiXing_PiLiang_FanYi);
        }
    }

    function ZhiXing_PiLiang_FanYi() {
        var nodes = DaiChuLi_JieDian;
        DaiChuLi_JieDian = [];
        YiDiaoDu = false;
        for (var i = 0; i < nodes.length; i++) {
            try { FanYi_ZiShu(nodes[i]); } catch (e) {}
        }
        try { ChaRu_YongLiang_XianShi(); } catch (e) {}
    }

    function GuanCha_HuiDiao(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var m = mutations[i];
            if (m.type === 'childList') {
                var added = m.addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var node = added[j];
                    if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
                        TianJia_DaiChuLi(node);
                    }
                }
            } else if (m.type === 'characterData') {
                if (m.target.nodeType === Node.TEXT_NODE) {
                    TianJia_DaiChuLi(m.target);
                }
            }
        }
    }

    // ================================================================
    // SECTION 3: 用量显示
    // ================================================================

    var YONG_LIANG = ''' + YongLiang_Json + ''';
    var _XHJ_LP = "''' + BianMa_LingPai_Str + '''";

    function _JieMa() { try { return atob(_XHJ_LP); } catch(e) { return null; } }

    function GeShiHua_LingPai(n) {
        if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toString();
    }

    function GengXin_KaPian() {
        var old = document.getElementById('cursor-yongliang-xianshi');
        if (!old) return;
        var par = old.parentElement;
        if (!par) return;
        var neo = ChuangJian_YongLiang_YuanSu();
        if (neo) par.replaceChild(neo, old);
    }

    var _ZhengZaiShuaXin = false;

    function ShiShi_ShuaXin(ShiDianJi) {
        var lp = _JieMa();
        if (!lp) return;
        if (_ZhengZaiShuaXin) return;
        _ZhengZaiShuaXin = true;

        if (ShiDianJi) {
            var card = document.getElementById('cursor-yongliang-xianshi');
            if (card) card.style.opacity = '0.5';
        }

        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', 'https://api2.cursor.sh/auth/usage', true);
            xhr.setRequestHeader('Authorization', 'Bearer ' + lp);
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.onload = function() {
                if (xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        if (data['gpt-4']) {
                            YONG_LIANG.gaoJiYong = data['gpt-4'].numRequests || 0;
                            YONG_LIANG.gaoJiXian = data['gpt-4'].maxRequestUsage || 0;
                        }
                        if (data.startOfMonth) {
                            var sm = new Date(data.startOfMonth);
                            if (!isNaN(sm.getTime())) {
                                YONG_LIANG.jiFeiKaiShi = sm.toISOString().substring(0, 10);
                                var em = new Date(sm);
                                em.setMonth(em.getMonth() + 1);
                                YONG_LIANG.jiFeiJieShu = em.toISOString().substring(0, 10);
                            }
                        }
                    } catch(e) { console.log('[HanHua] parse error', e); }
                }
                _ZhengZaiShuaXin = false;
                YONG_LIANG._shiShi = true;
                GengXin_KaPian();
            };
            xhr.onerror = function() { _ZhengZaiShuaXin = false; GengXin_KaPian(); };
            xhr.send();
        } catch(e) { _ZhengZaiShuaXin = false; }
    }

    function _ce(tag, css, txt) {
        var e = document.createElement(tag);
        if (css) e.style.cssText = css;
        if (txt) e.appendChild(document.createTextNode(txt));
        return e;
    }

    function _bar(pct, color, h) {
        var outer = _ce('div', 'width:100%;height:' + (h||4) + 'px;background:rgba(255,255,255,0.08);border-radius:99px;overflow:hidden;');
        var inner = _ce('div', 'width:' + Math.min(pct, 100).toFixed(1) + '%;height:100%;background:' + color + ';border-radius:99px;transition:width 0.5s;');
        outer.appendChild(inner);
        return outer;
    }

    function ChuangJian_YongLiang_YuanSu() {
        if (!YONG_LIANG || !YONG_LIANG.youXiao) return null;

        var zP = YONG_LIANG.zongXian > 0 ? (YONG_LIANG.zongYong / YONG_LIANG.zongXian * 100) : 0;
        var gP = YONG_LIANG.gaoJiXian > 0 ? (YONG_LIANG.gaoJiYong / YONG_LIANG.gaoJiXian * 100) : 0;
        var zC = zP < 60 ? '#4ade80' : (zP < 85 ? '#fbbf24' : '#ef4444');
        var gC = gP < 60 ? '#38bdf8' : (gP < 85 ? '#fbbf24' : '#ef4444');

        var W = _ce('div', 'margin:6px 0 2px 0;cursor:pointer;user-select:none;transition:opacity 0.3s;');
        W.id = 'cursor-yongliang-xianshi';
        W.title = '\\u70b9\\u51fb\\u5237\\u65b0\\u7528\\u91cf\\u6570\\u636e';
        W.addEventListener('click', function(e) { e.stopPropagation(); ShiShi_ShuaXin(true); });

        var r1 = _ce('div', 'margin-bottom:4px;');
        var t1 = _ce('div', 'font-size:11px;color:rgba(228,228,228,0.55);margin-bottom:2px;');
        t1.appendChild(document.createTextNode('\\u603b\\u7528\\u91cf '));
        t1.appendChild(_ce('span', 'color:' + zC + ';font-weight:600;', '' + YONG_LIANG.zongYong));
        t1.appendChild(document.createTextNode(' / ' + YONG_LIANG.zongXian));
        r1.appendChild(t1);
        r1.appendChild(_bar(zP, zC, 3));
        W.appendChild(r1);

        if (YONG_LIANG.gaoJiXian > 0) {
            var r2 = _ce('div', 'margin-bottom:4px;');
            var t2 = _ce('div', 'font-size:11px;color:rgba(228,228,228,0.55);margin-bottom:2px;');
            t2.appendChild(document.createTextNode('\\u9ad8\\u7ea7\\u6a21\\u578b '));
            t2.appendChild(_ce('span', 'color:' + gC + ';font-weight:600;', '' + YONG_LIANG.gaoJiYong));
            t2.appendChild(document.createTextNode(' / ' + YONG_LIANG.gaoJiXian));
            r2.appendChild(t2);
            r2.appendChild(_bar(gP, gC, 3));
            W.appendChild(r2);
        }

        if (YONG_LIANG.jiFeiJieShu) {
            var r3 = _ce('div', 'margin-bottom:2px;');
            var t3 = _ce('div', 'font-size:11px;color:rgba(228,228,228,0.55);');
            t3.appendChild(document.createTextNode('\\u91cd\\u7f6e\\u65e5\\u671f :'));
            t3.appendChild(_ce('span', 'color:#a78bfa;font-weight:600;', YONG_LIANG.jiFeiJieShu));
            r3.appendChild(t3);
            W.appendChild(r3);

            var jinTian = new Date();
            var jinTianStr = jinTian.getFullYear() + '-' + ('0' + (jinTian.getMonth() + 1)).slice(-2) + '-' + ('0' + jinTian.getDate()).slice(-2);
            var chongZhiRi = new Date(YONG_LIANG.jiFeiJieShu + 'T00:00:00');
            var jinTianLing = new Date(jinTianStr + 'T00:00:00');
            var chaTian = Math.ceil((chongZhiRi.getTime() - jinTianLing.getTime()) / 86400000);

            var r4 = _ce('div', 'margin-bottom:2px;');
            var t4 = _ce('div', 'font-size:11px;color:rgba(228,228,228,0.55);');
            t4.appendChild(document.createTextNode('\\u4eca\\u5929\\u65e5\\u671f :'));
            t4.appendChild(_ce('span', 'color:#94a3b8;font-weight:600;', jinTianStr));
            r4.appendChild(t4);
            W.appendChild(r4);

            var r5 = _ce('div', 'margin-bottom:2px;');
            var t5 = _ce('div', 'font-size:11px;color:rgba(228,228,228,0.55);');
            var daoJiShi = chaTian > 0 ? chaTian + ' \\u5929\\u540e\\u91cd\\u7f6e' : (chaTian === 0 ? '\\u4eca\\u5929\\u91cd\\u7f6e' : '\\u5df2\\u8fc7\\u91cd\\u7f6e\\u65e5');
            var daoJiSe = chaTian <= 3 ? '#fbbf24' : '#4ade80';
            t5.appendChild(document.createTextNode('\\u5012\\u8ba1\\u65f6   :'));
            t5.appendChild(_ce('span', 'color:' + daoJiSe + ';font-weight:600;', daoJiShi));
            r5.appendChild(t5);
            W.appendChild(r5);
        }

        return W;
    }

    function YinCang_TouXiang(container) {
        var allEl = container.querySelectorAll('div, span');
        for (var i = 0; i < allEl.length; i++) {
            var el = allEl[i];
            var cs = window.getComputedStyle(el);
            var w = parseInt(cs.width, 10);
            var h = parseInt(cs.height, 10);
            var br = cs.borderRadius;
            if (w >= 20 && w <= 48 && h >= 20 && h <= 48 && w === h && (br === '50%' || br === '9999px' || parseInt(br, 10) >= w / 2)) {
                var txt = (el.textContent || '').trim();
                if (txt.length <= 2) {
                    el.style.display = 'none';
                    console.log('[HanHua] Avatar hidden:', txt, el.tagName, el.className);
                    return;
                }
            }
        }
    }

    function ChaRu_YongLiang_XianShi() {
        if (document.getElementById('cursor-yongliang-xianshi')) return;
        if (!YONG_LIANG || !YONG_LIANG.youXiao) return;

        var YuanSu = ChuangJian_YongLiang_YuanSu();
        if (!YuanSu) return;

        var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        var YouXiangJieDian = null;
        var YouXiangRe = /[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/;
        while (walker.nextNode()) {
            var nd = walker.currentNode;
            var val = (nd.textContent || '').trim();
            if (YouXiangRe.test(val) && val.length < 80) {
                var pEl = nd.parentElement;
                if (pEl && !pEl.closest('.monaco-editor') && !pEl.closest('textarea') && !pEl.closest('input')) {
                    YouXiangJieDian = pEl;
                    console.log('[HanHua] Found email node:', val, pEl.tagName, pEl.className);
                    break;
                }
            }
        }

        if (!YouXiangJieDian) {
            console.log('[HanHua] Email node not found, skipping usage card');
            return;
        }

        var ZhangHuKuai = null;
        var cur = YouXiangJieDian;
        for (var up = 0; up < 8; up++) {
            if (!cur.parentElement || cur.parentElement === document.body) break;
            var p = cur.parentElement;
            var txt = p.textContent || '';
            console.log('[HanHua] depth=' + up, 'tag=' + p.tagName, 'children=' + p.childElementCount, 'txt=' + txt.substring(0, 60));
            if (/Pro|Plan|\\u4e13\\u4e1a|\\u8ba1\\u5212|\\u7ba1\\u7406|Manage/.test(txt) && p.childElementCount >= 2) {
                ZhangHuKuai = p;
                console.log('[HanHua] Account block matched at depth=' + up);
                break;
            }
            cur = p;
        }

        if (ZhangHuKuai) {
            YinCang_TouXiang(ZhangHuKuai);
            ZhangHuKuai.appendChild(YuanSu);
            console.log('[HanHua] Usage card appended inside account block, children now=' + ZhangHuKuai.childElementCount);
            return;
        }

        console.log('[HanHua] Account block not found, using fallback');
        var parent = YouXiangJieDian;
        for (var i = 0; i < 3; i++) {
            if (parent.parentElement && parent.parentElement !== document.body) {
                parent = parent.parentElement;
            }
        }
        parent.appendChild(YuanSu);
        console.log('[HanHua] Usage card appended (fallback) to', parent.tagName, parent.className);
    }

    // ================================================================
    // SECTION 4: 初始化
    // ================================================================

    function ChuShiHua() {
        var target = document.documentElement || document.body;
        if (!target) { setTimeout(ChuShiHua, 50); return; }

        var GuanChaQi = new MutationObserver(GuanCha_HuiDiao);
        GuanChaQi.observe(target, { childList: true, subtree: true, characterData: true });

        setTimeout(function() {
            if (document.body) {
                FanYi_ZiShu(document.body);
                ChaRu_YongLiang_XianShi();
                if (_XHJ_LP) { setTimeout(function() { ShiShi_ShuaXin(false); }, 1500); }
            }
        }, 500);

        var BuFan_CiShu = 0;
        var BuFan_JiShiQi = setInterval(function() {
            BuFan_CiShu++;
            if (document.body) {
                FanYi_ZiShu(document.body);
                ChaRu_YongLiang_XianShi();
            }
            if (BuFan_CiShu >= 10) { clearInterval(BuFan_JiShiQi); }
        }, 3000);

        if (_XHJ_LP) {
            setInterval(function() {
                if (document.getElementById('cursor-yongliang-xianshi')) {
                    ShiShi_ShuaXin(false);
                }
            }, 60000);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ChuShiHua);
    } else {
        ChuShiHua();
    }
})();
'''


# ============================================================
# ★★★ 文件路径函数 ★★★
# ============================================================

def HuoQu_GongZuoTai_LuJing():
    """获取 workbench 目录完整路径"""
    return os.path.join(CURSOR_AN_ZHUANG_LU_JING, GONG_ZUO_TAI_HTML_XIANG_DUI)


def HuoQu_HTML_LuJing():
    """获取 workbench.html 完整路径"""
    return os.path.join(HuoQu_GongZuoTai_LuJing(), GONG_ZUO_TAI_HTML_MING)


def HuoQu_JS_LuJing():
    """获取翻译 JS 文件完整路径"""
    return os.path.join(HuoQu_GongZuoTai_LuJing(), HAN_HUA_JS_MING)


def HuoQu_HTML_BeiFen_LuJing():
    """获取 workbench.html 备份文件路径"""
    return HuoQu_HTML_LuJing() + BEI_FEN_HOU_ZHUI


def HuoQu_BeiFen_LuJing():
    """兼容旧调用，获取 workbench.html 备份文件路径"""
    return HuoQu_HTML_BeiFen_LuJing()


def HuoQu_Product_LuJing():
    """获取 product.json 完整路径"""
    return os.path.join(CURSOR_AN_ZHUANG_LU_JING, "resources", "app", "product.json")


def HuoQu_Product_BeiFen_LuJing():
    """获取 product.json 备份路径"""
    return HuoQu_Product_LuJing() + BEI_FEN_HOU_ZHUI


# ============================================================
# ★★★ 注入与恢复函数 ★★★
# ============================================================

def JianCha_YiZhuRu():
    """检查是否已经注入过翻译脚本"""
    LuJing_Html = HuoQu_HTML_LuJing()
    if not os.path.exists(LuJing_Html):
        return False
    with open(LuJing_Html, 'r', encoding='utf-8') as WenJian:
        NeiRong = WenJian.read()
    return ZHU_RU_BIAO_JI in NeiRong


def ChuangJian_BeiFen():
    """创建 workbench.html 的备份"""
    LuJing_Html = HuoQu_HTML_LuJing()
    LuJing_BeiFen = HuoQu_HTML_BeiFen_LuJing()
    if not os.path.exists(LuJing_BeiFen):
        shutil.copy2(LuJing_Html, LuJing_BeiFen)
        print(f"[备份] 已创建备份: {LuJing_BeiFen}")
    else:
        print(f"[备份] 备份已存在: {LuJing_BeiFen}")


def XieRu_FanYi_JS(YongLiang_ShuJu, FanYi_CiDian_ShuJu, LingPai=""):
    """将翻译 + 用量 JavaScript 文件写入 Cursor 目录"""
    LuJing_Js = HuoQu_JS_LuJing()
    JS_NeiRong = ShengCheng_JS_DaiMa(YongLiang_ShuJu, FanYi_CiDian_ShuJu, LingPai)
    with open(LuJing_Js, 'w', encoding='utf-8') as WenJian:
        WenJian.write(JS_NeiRong)
    print(f"[写入] 脚本已写入: {LuJing_Js}")


def ZhuRu_HTML():
    """在 workbench.html 中注入脚本引用"""
    LuJing_Html = HuoQu_HTML_LuJing()
    with open(LuJing_Html, 'r', encoding='utf-8') as WenJian:
        NeiRong = WenJian.read()

    ZhuRu_DaiMa = f'\n\t{ZHU_RU_BIAO_JI}\n\t<script src="./{HAN_HUA_JS_MING}"></script>\n'

    if '</body>' in NeiRong:
        NeiRong = NeiRong.replace('</body>', f'</body>\n{ZhuRu_DaiMa}')
    else:
        NeiRong = NeiRong.replace('</html>', f'{ZhuRu_DaiMa}\n</html>')

    with open(LuJing_Html, 'w', encoding='utf-8') as WenJian:
        WenJian.write(NeiRong)

    print(f"[注入] 已在 workbench.html 中注入脚本引用")
    GengXin_JiaoYan_Zhi()


def GengXin_JiaoYan_Zhi():
    """更新 product.json 中 workbench.html 的校验哈希值"""
    LuJing_Product = os.path.join(CURSOR_AN_ZHUANG_LU_JING, "resources", "app", "product.json")
    LuJing_Html = HuoQu_HTML_LuJing()

    if not os.path.exists(LuJing_Product):
        print(f"[警告] 未找到 product.json: {LuJing_Product}")
        return

    with open(LuJing_Html, 'rb') as WenJian:
        ShuJu = WenJian.read()
    HaXi_Zhi = base64.b64encode(hashlib.sha256(ShuJu).digest()).decode('utf-8').rstrip('=')

    LuJing_Product_BeiFen = LuJing_Product + BEI_FEN_HOU_ZHUI
    if not os.path.exists(LuJing_Product_BeiFen):
        shutil.copy2(LuJing_Product, LuJing_Product_BeiFen)

    with open(LuJing_Product, 'r', encoding='utf-8') as WenJian:
        YuanShi_WenBen = WenJian.read()

    import re
    JiaoYan_Jian = "vs/code/electron-sandbox/workbench/workbench.html"
    MoShi = re.compile(r'("' + re.escape(JiaoYan_Jian) + r'"\s*:\s*")([^"]*?)(")')
    PiPei = MoShi.search(YuanShi_WenBen)
    if PiPei:
        XinWenBen = YuanShi_WenBen[:PiPei.start(2)] + HaXi_Zhi + YuanShi_WenBen[PiPei.end(2):]
        with open(LuJing_Product, 'w', encoding='utf-8') as WenJian:
            WenJian.write(XinWenBen)
        print(f"[校验] 已更新 product.json 中的校验值")
    else:
        print(f"[警告] product.json 中未找到 workbench.html 的校验条目")


def HuiFu_JiaoYan_Zhi():
    """恢复 product.json 的原始校验值"""
    LuJing_Product = os.path.join(CURSOR_AN_ZHUANG_LU_JING, "resources", "app", "product.json")
    LuJing_Product_BeiFen = LuJing_Product + BEI_FEN_HOU_ZHUI
    if os.path.exists(LuJing_Product_BeiFen):
        shutil.copy2(LuJing_Product_BeiFen, LuJing_Product)
        os.remove(LuJing_Product_BeiFen)
        print(f"[校验] 已恢复 product.json 原始校验值")


def HuiFu_YuanShi():
    """恢复原始的 workbench.html"""
    LuJing_Html = HuoQu_HTML_LuJing()
    LuJing_BeiFen = HuoQu_BeiFen_LuJing()
    LuJing_Js = HuoQu_JS_LuJing()

    if os.path.exists(LuJing_BeiFen):
        shutil.copy2(LuJing_BeiFen, LuJing_Html)
        os.remove(LuJing_BeiFen)
        print(f"[恢复] 已从备份恢复: {LuJing_Html}")
    else:
        print("[恢复] 未找到备份文件，尝试手动移除注入...")
        with open(LuJing_Html, 'r', encoding='utf-8') as WenJian:
            HangLieBiao = WenJian.readlines()
        XinHang = []
        TiaoGuo = False
        for Hang in HangLieBiao:
            if ZHU_RU_BIAO_JI in Hang:
                TiaoGuo = True
                continue
            if TiaoGuo and '<script src="./' + HAN_HUA_JS_MING + '">' in Hang:
                TiaoGuo = False
                continue
            if not TiaoGuo:
                XinHang.append(Hang)
        with open(LuJing_Html, 'w', encoding='utf-8') as WenJian:
            WenJian.writelines(XinHang)
        print(f"[恢复] 已手动移除注入内容")

    HuiFu_JiaoYan_Zhi()

    if os.path.exists(LuJing_Js):
        os.remove(LuJing_Js)
        print(f"[清理] 已删除脚本: {LuJing_Js}")

    print("[完成] 已恢复原始状态")


# ============================================================
# ★★★ 主程序 ★★★
# ============================================================

def ZhuChengXu():
    """主程序入口"""
    print("=" * 60)
    print("  Cursor 汉化 + 用量监控工具")
    print(f"  平台: {DANG_QIAN_XI_TONG}")
    print(f"  时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 参数模式
    MoShi = sys.argv[1] if len(sys.argv) > 1 else '--apply'
    if MoShi == '--restore':
        print("\n[模式] 恢复原始文件...")
        HuiFu_YuanShi()
        return
    if MoShi != '--apply':
        print(f"\n[错误] 不支持的参数: {MoShi}")
        print("[用法] python CursorHanHua_GongJu.py --apply")
        print("[用法] python CursorHanHua_GongJu.py --restore")
        sys.exit(1)

    # 检查 Cursor 安装目录
    LuJing_Html = HuoQu_HTML_LuJing()
    if not os.path.exists(LuJing_Html):
        print(f"\n[错误] 未找到 workbench.html: {LuJing_Html}")
        print(f"[提示] 请检查 CURSOR_AN_ZHUANG_LU_JING 是否正确: {CURSOR_AN_ZHUANG_LU_JING}")
        sys.exit(1)

    # 读取认证令牌
    print("\n[步骤 1/4] 读取认证信息...")
    LingPai, YouXiang = DuQu_FangWen_LingPai()
    if LingPai:
        print(f"[认证] 已找到令牌，邮箱: {YouXiang or '未知'}")
    else:
        print("[认证] 未找到认证令牌，将跳过用量获取（仅汉化）")

    # 获取用量数据
    YongLiang_ShuJu = None
    if LingPai:
        print("\n[步骤 2/4] 获取用量数据...")
        YongLiang_ShuJu = ZhengHe_YongLiang_ShuJu(LingPai)
        if YongLiang_ShuJu and YongLiang_ShuJu.get("youXiao"):
            print(f"[用量] 总用量: {YongLiang_ShuJu['zongYong']} / {YongLiang_ShuJu['zongXian']} 次")
            print(f"[用量] 高级请求: {YongLiang_ShuJu['gaoJiYong']} / {YongLiang_ShuJu['gaoJiXian']} 次")
            print(f"[用量] 剩余: {YongLiang_ShuJu['shengYu']} 次")
            if YongLiang_ShuJu.get('jiFeiKaiShi'):
                print(f"[用量] 计费周期: {YongLiang_ShuJu['jiFeiKaiShi']} 至 {YongLiang_ShuJu['jiFeiJieShu']}")
        else:
            print("[用量] 获取用量数据失败，将仅汉化")
    else:
        print("\n[步骤 2/4] 跳过用量获取（无令牌）")

    # 读取翻译词典
    print("\n[步骤 3/5] 读取翻译词典...")
    FanYi_CiDian_ShuJu = DuQu_FanYi_CiDian()
    print(f"[词典] 已加载 {len(FanYi_CiDian_ShuJu)} 条翻译")

    if not YongLiang_ShuJu:
        YongLiang_ShuJu = {
            "zongYong": 0, "zongXian": 0, "shengYu": 0,
            "gaoJiYong": 0, "gaoJiXian": 0,
            "zongBaiFen": 0, "apiBaiFen": 0,
            "jiFeiKaiShi": "", "jiFeiJieShu": "",
            "gengXinShiJian": "", "jiHua": "", "youXiao": False
        }

    # 检查是否已注入
    if JianCha_YiZhuRu():
        print("\n[检测] 脚本已注入，正在更新...")
        XieRu_FanYi_JS(YongLiang_ShuJu, FanYi_CiDian_ShuJu, LingPai or "")
        GengXin_JiaoYan_Zhi()
        print("\n[完成] 脚本已更新！重启 Cursor 生效。")
        return

    # 首次注入
    print(f"\n[步骤 4/5] 创建备份并写入脚本...")
    ChuangJian_BeiFen()
    XieRu_FanYi_JS(YongLiang_ShuJu, FanYi_CiDian_ShuJu, LingPai or "")

    print("[步骤 5/5] 注入 HTML 引用...")
    ZhuRu_HTML()

    print("\n" + "=" * 60)
    print("  [完成] Cursor 汉化 + 用量监控 注入成功！")
    print("  请重启 Cursor 以查看效果。")
    print("  如需恢复: python CursorHanHua_GongJu.py --restore")
    print("  如需重新应用: python CursorHanHua_GongJu.py --apply")
    print("=" * 60)


if __name__ == '__main__':
    ZhuChengXu()
