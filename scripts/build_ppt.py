"""Generate a clean, plain-language 11-slide 16:9 defense PPTX in results/final/presentation.pptx."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "results" / "final"
FIGDIR = FINAL / "figures"
OUT_PPT = FINAL / "presentation.pptx"

NAVY = RGBColor(0x1E, 0x3A, 0x5F)
DARK = RGBColor(0x1F, 0x29, 0x37)
MUTED = RGBColor(0x4B, 0x55, 0x63)
LIGHT_BG = RGBColor(0xF8, 0xFA, 0xFC)
CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)
BORDER = RGBColor(0xCB, 0xD5, 0xE1)
BLUE = RGBColor(0x25, 0x63, 0xEB)
ORANGE = RGBColor(0xEA, 0x58, 0x0C)
PURPLE = RGBColor(0x7C, 0x3A, 0xED)
GREEN = RGBColor(0x16, 0xA3, 0x4A)
TINT_BLUE = RGBColor(0xEF, 0xF6, 0xFF)
TINT_AMBER = RGBColor(0xFF, 0xF7, 0xED)
TINT_PURPLE = RGBColor(0xF5, 0xF3, 0xFF)
TINT_GREEN = RGBColor(0xF0, 0xFD, 0xF4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT_CN = "PingFang SC"
TOTAL_PAGES = 13


def set_bg(slide, color):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_header(slide, section: str, title: str, page_num: int):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.10))
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()

    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.22), Inches(11.8), Inches(0.85))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p0 = tf.paragraphs[0]
    r0 = p0.add_run()
    r0.text = section
    r0.font.name = FONT_CN
    r0.font.size = Pt(11.5)
    r0.font.bold = True
    r0.font.color.rgb = BLUE

    p1 = tf.add_paragraph()
    p1.space_before = Pt(2)
    r1 = p1.add_run()
    r1.text = title
    r1.font.name = FONT_CN
    r1.font.size = Pt(22.5)
    r1.font.bold = True
    r1.font.color.rgb = NAVY

    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.12), Inches(12.133), Inches(0.02))
    line.fill.solid()
    line.fill.fore_color.rgb = BORDER
    line.line.fill.background()

    ft = slide.shapes.add_textbox(Inches(0.6), Inches(7.12), Inches(12.133), Inches(0.28))
    ftf = ft.text_frame
    ftf.margin_left = ftf.margin_top = ftf.margin_right = ftf.margin_bottom = 0
    fp = ftf.paragraphs[0]
    fp.alignment = PP_ALIGN.RIGHT
    fr = fp.add_run()
    fr.text = f"TCP 拥塞控制的智能参数调优研究  |  {page_num} / {TOTAL_PAGES}"
    fr.font.name = FONT_CN
    fr.font.size = Pt(10)
    fr.font.color.rgb = MUTED


def add_card(slide, left, top, width, height, title: str, bullets: list[str],
             accent=NAVY, bg=CARD_BG, title_size=14, body_size=12.4):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    box.adjustments[0] = 0.04
    box.fill.solid()
    box.fill.fore_color.rgb = bg
    box.line.color.rgb = BORDER
    box.line.width = Pt(1)

    strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top + 0.08), Inches(0.08), Inches(height - 0.16))
    strip.fill.solid()
    strip.fill.fore_color.rgb = accent
    strip.line.fill.background()

    tb = slide.shapes.add_textbox(Inches(left + 0.22), Inches(top + 0.14), Inches(width - 0.34), Inches(height - 0.24))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    p0 = tf.paragraphs[0]
    r0 = p0.add_run()
    r0.text = title
    r0.font.name = FONT_CN
    r0.font.size = Pt(title_size)
    r0.font.bold = True
    r0.font.color.rgb = accent

    for item in bullets:
        p = tf.add_paragraph()
        p.space_before = Pt(5.5)
        r = p.add_run()
        r.text = f"• {item}"
        r.font.name = FONT_CN
        r.font.size = Pt(body_size)
        r.font.color.rgb = DARK


def add_banner(slide, left, top, width, height, text: str, bg=TINT_BLUE, color=NAVY, size=13.5):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    box.adjustments[0] = 0.12
    box.fill.solid()
    box.fill.fore_color.rgb = bg
    box.line.color.rgb = color
    box.line.width = Pt(0.75)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Inches(0.18)
    tf.margin_right = Inches(0.18)
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.name = FONT_CN
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = color


def add_picture_fit(slide, img_path: Path, left: float, top: float, max_w: float, max_h: float):
    from PIL import Image
    with Image.open(img_path) as im:
        iw, ih = im.size
    ratio = min(max_w / iw, max_h / ih)
    w, h = iw * ratio, ih * ratio
    x = left + (max_w - w) / 2
    y = top + (max_h - h) / 2
    slide.shapes.add_picture(str(img_path), Inches(x), Inches(y), width=Inches(w), height=Inches(h))


def set_notes(slide, text: str):
    slide.notes_slide.notes_text_frame.text = text


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # ==================== SLIDE 1: COVER ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, NAVY)
    deco = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(6.75), Inches(13.333), Inches(0.75))
    deco.fill.solid()
    deco.fill.fore_color.rgb = RGBColor(0x13, 0x26, 0x42)
    deco.line.fill.background()

    accent_line = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.95), Inches(1.55), Inches(1.2), Inches(0.08))
    accent_line.fill.solid()
    accent_line.fill.fore_color.rgb = RGBColor(0x38, 0xBD, 0xF8)
    accent_line.line.fill.background()

    tb = s.shapes.add_textbox(Inches(0.95), Inches(1.85), Inches(11.4), Inches(3.2))
    tf = tb.text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    r.text = "网络技术综合实习 · 专题汇报"
    r.font.name = FONT_CN
    r.font.size = Pt(16)
    r.font.color.rgb = RGBColor(0x93, 0xC5, 0xFD)

    p2 = tf.add_paragraph()
    p2.space_before = Pt(14)
    r2 = p2.add_run()
    r2.text = "TCP 拥塞控制的智能参数调优研究"
    r2.font.name = FONT_CN
    r2.font.size = Pt(40)
    r2.font.bold = True
    r2.font.color.rgb = WHITE

    p3 = tf.add_paragraph()
    p3.space_before = Pt(16)
    r3 = p3.add_run()
    r3.text = "基于 ns-3 复现 Reno / CUBIC 窗口曲线，并用 GLM-4-Flash 动态调整慢开始阈值"
    r3.font.name = FONT_CN
    r3.font.size = Pt(18)
    r3.font.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)

    mt = s.shapes.add_textbox(Inches(0.95), Inches(5.35), Inches(11.4), Inches(1.1))
    mr = mt.text_frame.paragraphs[0].add_run()
    mr.text = "小组成员：XXX、XXX（请填写）     |     汇报人：XXX     |     日期：2026 年 11 月"
    mr.font.name = FONT_CN
    mr.font.size = Pt(14)
    mr.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)

    ft = s.shapes.add_textbox(Inches(0.95), Inches(6.92), Inches(11.4), Inches(0.4))
    fr = ft.text_frame.paragraphs[0].add_run()
    fr.text = "技术栈：ns-3.49 离散事件仿真  ·  Python 3.12  ·  智谱 GLM-4-Flash（免费 API）"
    fr.font.name = FONT_CN
    fr.font.size = Pt(12.5)
    fr.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    set_notes(s, "各位老师、同学大家好，今天汇报的课题是《TCP拥塞控制的智能参数调优研究》。我们基于 ns-3 复现了经典的 Reno 和 CUBIC 拥塞窗口曲线，设计了基于 GLM-4-Flash 的动态调参策略，对比了三者在多种网络条件下的吞吐量、时延与公平性，最后讨论了“AI 替代固定 AIMD 参数”的可行性。")

    # ==================== SLIDE 2: BACKGROUND & GOALS ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "01  研究背景与课题目标", "固定 AIMD 参数在动态网络中的问题", 2)

    add_card(s, 0.6, 1.38, 5.85, 2.38, "经典算法的固定参数做法", [
        "TCP Reno：无丢包线性加 1 MSS，丢包后固定把窗口折半（保留比例 β = 0.5）",
        "TCP CUBIC（Linux 默认）：三次函数曲线恢复，丢包后固定保留 70%（β = 0.7）",
        "共同假设：默认把所有丢包都当成路由器队列满载拥塞",
    ], accent=BLUE)

    add_card(s, 6.85, 1.38, 5.88, 2.38, "现实动态网络中遇到的问题", [
        "无线随机丢包：队列本来是空的，误判砍窗导致吞吐量大幅下降",
        "带宽突然下降：β 太大会让大量数据包积压在队列里，端到端时延飙升",
        "路由切换或浅缓冲：β 太小容易排空队列，导致高速链路跑不满",
    ], accent=ORANGE)

    add_banner(
        s, 0.6, 4.02, 12.13, 0.85,
        "核心任务：复现 Reno / CUBIC 曲线，用 GLM-4-Flash 动态调整慢开始阈值，并评估“AI 替代固定 AIMD 参数”的可行性",
        bg=TINT_BLUE, color=NAVY, size=13.5,
    )

    add_card(s, 0.6, 5.12, 3.82, 1.75, "研究内容 1 · 协议复现", [
        "准确复现慢开始、拥塞避免、快重传、快恢复四阶段",
        "相同条件下对比 Reno 与 CUBIC 窗口曲线",
    ], accent=NAVY, bg=TINT_BLUE, title_size=13.5, body_size=12)

    add_card(s, 4.75, 5.12, 3.82, 1.75, "研究内容 2 · 可解释指标调参", [
        "只用发送端可测的 RTT、吞吐和重传指标",
        "用 GLM-4-Flash 动态调整保留比例 β",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=13.5, body_size=12)

    add_card(s, 8.91, 5.12, 3.82, 1.75, "研究内容 3 · 公平性与可行性", [
        "Reno、CUBIC、AI 三条流同场竞争测公平性",
        "结合效果和响应耗时评估工程可行性",
    ], accent=GREEN, bg=TINT_GREEN, title_size=13.5, body_size=12)

    set_notes(s, "课本里的 Reno 丢包固定折半，Linux 默认的 CUBIC 固定保留 0.7，它们都把丢包一刀切当成拥塞。我们的工作主要围绕三部分展开：复现四阶段和两条曲线、用可解释指标驱动 GLM-4-Flash 动态调参、测试三流公平性并分析可行性。")

    # ==================== SLIDE 3: CORE CONCEPTS ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "02  基本原理速览", "四阶段流程、带宽时延积与网络状态判断方法", 3)

    add_card(s, 0.6, 1.38, 3.85, 5.45, "1. 课本四阶段核心流程", [
        "拥塞窗口 cwnd：收到 ACK 前允许在途的数据量（1 MSS = 1448 B）",
        "慢开始阈值 ssthresh：指数增长和线性增长的分界线",
        "慢开始：cwnd < ssthresh，每 RTT 窗口翻倍",
        "拥塞避免：cwnd >= ssthresh，每 RTT 线性加 1 MSS",
        "快重传：连收 3 个重复 ACK 立即补发缺失包",
        "快恢复：按比例 β 更新 ssthresh，不退回 1 MSS",
    ], accent=BLUE, title_size=14, body_size=12)

    add_card(s, 4.74, 1.38, 3.85, 5.45, "2. 带宽时延积 BDP 与队列", [
        "BDP = 带宽 × 基础往返时延（填满链路水管的数据量）",
        "14 Mbit/s × 44 ms ≈ 77 KB（队列 ≈ 1 BDP）：β=0.5 恰跑满",
        "扩容至 40 Mbit/s（队列 ≈ 0.34 BDP）：浅缓冲需调高 β=0.7",
        "骤降至 3 Mbit/s（队列 ≈ 4.5 BDP）：深缓冲需压低 β=0.4",
        "三档带宽对应三种不同的最优保留比例",
        "单一固定 β 难以在不同带宽条件下两全",
    ], accent=ORANGE, title_size=14, body_size=12)

    add_card(s, 8.88, 1.38, 3.85, 5.45, "3. 发送端如何判断网络状态", [
        "RTT 膨胀率 = (窗口平均 RTT / 历史最小 RTT) − 1",
        "无线随机丢包：持续重传但 RTT 紧贴最小 RTT（队列空）→ 调高 β = 0.8",
        "带宽骤降拥塞：RTT 翻倍升高且吞吐大跌 → 调低 β = 0.4 排空队列",
        "路由时延增加：RTT 整体升高但吞吐维持高位 → 调高 β = 0.7 保吞吐",
        "常规/多流竞争：中等排队且吞吐正常 → 回到标准 β = 0.5",
        "全部指标均取自发送端直接观测",
    ], accent=PURPLE, title_size=14, body_size=12)

    set_notes(s, "这里用通俗的方式回顾三个概念：TCP 四阶段机制、带宽时延积与队列深度的关系，以及如何只看发送端的 RTT、吞吐和重传，区分随机丢包、带宽拥塞、路由时延增加和常规竞争四种情况。")

    # ==================== SLIDE 4: DESIGN ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "03  仿真平台与 AI 策略设计", "聚焦 Reno、CUBIC、GLM-4-Flash 三大角色，共 72 次仿真", 4)

    add_card(s, 0.6, 1.38, 5.85, 2.55, "哑铃型仿真拓扑与统一接口", [
        "发送端/接收端以 1 Gbit/s（1 ms）接入，共享瓶颈默认 20 Mbit/s（20 ms）",
        "端到端基础往返时延 44 ms，路由器采用 FIFO 队列",
        "AI 策略在 Reno 基础上仅开放 β 接口：ssthresh = MSS × max(2, floor(β·cwnd/MSS))",
        "β 可选 {0.4, 0.5, 0.6, 0.7, 0.8}，确保对比只反映动态调参效果",
    ], accent=NAVY, body_size=12.2)

    add_card(s, 6.85, 1.38, 5.88, 2.55, "清晰简洁的对照角色（alg 配置）", [
        "reno：标准 TCP Reno（固定 β = 0.5）",
        "cubic：Linux 默认 TCP CUBIC（固定 β = 0.7，三次曲线）",
        "glm：基于 GLM-4-Flash 的 AI 动态调优策略",
        "fixed：仅在实验三用于标定三档带宽的理论预期 β 倾向（16 项单测全过）",
    ], accent=BLUE, body_size=12.2)

    add_card(s, 0.6, 4.18, 12.13, 2.68, "GLM-4-Flash 的核心设计：定期综合评估 + 本地即时执行", [
        "为何避免逐包或每秒调用？大模型单次远程响应中位约 2.24 秒，远慢于 44 ms 的 RTT，且单秒数据抖动大",
        "我们的做法：每 8 秒汇总一次近期纯数值 RTT 涨幅、吞吐占比、波动度和重传比例，状态剧烈跳变时提前触发评估",
        "大模型直接依据数值输出中文判断依据、状态和目标 β；两次评估之间，发送端按当前 β 在本地响应每次丢包",
        "实际效果：单条 AI 流在 55～85 秒连接中平均仅需调用 8.2 次免费 API，既省时稳定，又能准确跟上网络变化",
    ], accent=PURPLE, bg=TINT_PURPLE, body_size=12.4)

    set_notes(s, "整个系统非常干净，只保留 reno、cubic 和 glm 三个主角。因为远程大模型每次回复中位约 2.24 秒，我们采用每 8 秒汇总一次纯数值指标做评估、状态剧烈跳变时提前触发、期间本地直接按当前 β 执行的方案，单条 AI 流平均只需调用 8.2 次 API。")

    # ==================== SLIDE 5: EXP 1A PROTOCOL PHASES ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "04  实验一：经典协议复现", "精确复现慢开始、拥塞避免、快重传与快恢复四阶段", 5)

    add_picture_fit(s, FIGDIR / "fig1_protocol_phases.png", 0.55, 1.32, 8.2, 5.65)

    add_card(s, 8.95, 1.38, 3.8, 3.25, "第 150 号包精确丢弃核验", [
        "初始 cwnd = 1 MSS，ssthresh = 32 MSS",
        "慢开始每 RTT 严格翻倍（1→2→4→8→16→32）",
        "1.4337 s：第 150 号包丢弃（cwnd = 35 MSS）",
        "1.4585 s：收到 3 个重复 ACK，触发快重传与快恢复，ssthresh 折半至 17.5 MSS",
        "1.5031 s：退出快恢复，继续线性增长",
    ], accent=BLUE, body_size=11.8)

    add_card(s, 8.95, 4.82, 3.8, 2.05, "数据核对结果", [
        "总交付 30,444,888 B，收发完全一致",
        "重传数据量恰好 1,448 B（1 个 MSS）",
        "队列丢包 0 次，无超时重传",
        "完整复现标准 TCP Reno 四阶段",
    ], accent=GREEN, bg=TINT_GREEN, body_size=11.8)

    set_notes(s, "实验 1a 首先验证标准四阶段。第 150 号包在 1.4337 秒丢弃后，仅隔 24.8 毫秒就收到 3 个重复 ACK 触发快重传和快恢复，慢开始阈值精确折半到 17.5 MSS，全程只重传了恰好 1448 字节，完全符合课本流程。")

    # ==================== SLIDE 6: EXP 1B RENO VS CUBIC ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "04  实验一：CUBIC 复现与 Reno 对比", "CUBIC 沿用慢开始/快重传框架，核心差异体现在稳态三次曲线与 β = 0.7", 6)

    add_picture_fit(s, FIGDIR / "fig2_reno_vs_cubic_zoom.png", 0.6, 1.35, 12.1, 3.85)

    add_card(s, 0.6, 5.32, 5.85, 1.62, "TCP CUBIC（橙线 · Linux 默认，固定 β = 0.7）", [
        "按距上次丢包的时间走三次曲线：108 MSS 快速拱形回升 → 近峰值 149 MSS 放缓试探",
        "吞吐 19.281 Mbit/s，队列丢包降 43.7%（0.1593%），但中位 RTT 升至 83.0 ms（+12 ms）",
    ], accent=ORANGE, bg=TINT_AMBER, title_size=13.3, body_size=11.8)

    add_card(s, 6.85, 5.32, 5.88, 1.62, "TCP Reno（蓝线 · 课本经典，固定 β = 0.5）", [
        "规整直线锯齿：150 MSS 丢包后直接折半至 ~76 MSS（贴合 BDP），再逐 RTT 线性加 1",
        "吞吐 19.280 Mbit/s，中位 RTT 71.0 ms（更低），队列丢包率 0.2829%",
    ], accent=BLUE, bg=TINT_BLUE, title_size=13.3, body_size=11.8)

    set_notes(s, "由于 CUBIC 和 Reno 共用相同的慢开始和快重传流程，区别主要体现在稳态拥塞避免阶段和丢包保留比例，所以我们紧接着在相同 20 Mbit/s 瓶颈下对比两者的稳态曲线。橙线 CUBIC 清晰呈现了“丢包后保留 70% 至 108 MSS → 快速拱形回升 → 逼近上次峰值 149 MSS 时放缓试探”的三次曲线特征，队列丢包比 Reno 少 43.7%，但中位 RTT 高出 12 ms。")

    # ==================== SLIDE 7: EXP 2A RANDOM LOSS METRICS ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "05  实验二：无线随机丢包（吞吐与时延）", "非拥塞随机丢包下，GLM-4-Flash 吞吐较 Reno 提速 57%～58% 且尾时延更低", 7)

    add_picture_fit(s, FIGDIR / "fig3_random_loss_metrics.png", 0.55, 1.32, 12.2, 4.15)

    add_card(s, 0.6, 5.56, 3.85, 1.40, "空队列却误判降窗", [
        "中位 RTT 全部贴近 44 ms（实测 46 ms），队列基本为空",
        "Reno 跌至 5.34 / 3.84 Mbit/s（比值 71.9% 贴合 1/√2）",
    ], accent=BLUE, title_size=13, body_size=11.4)

    add_card(s, 4.74, 5.56, 3.85, 1.40, "CUBIC 反而低于 Reno", [
        "仅 4.67 / 3.17 Mbit/s（较 Reno 再低 12.6% / 17.5%）",
        "高频随机丢包反复误触发快速收敛（×0.85），窗口越压越低",
    ], accent=ORANGE, bg=TINT_AMBER, title_size=13, body_size=11.4)

    add_card(s, 8.88, 5.56, 3.85, 1.40, "GLM-4-Flash 吞吐与尾时延双优", [
        "有效吞吐升至 8.44 / 6.03 Mbit/s（较 CUBIC +81%～90%）",
        "P95 尾时延降至 50.2 / 53.0 ms，单次仅调 7 次 API",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=13, body_size=11.4)

    set_notes(s, "实验二左图展示吞吐量，右图展示中位 RTT 和 P95 尾时延。可以看到三者中位 RTT 都紧贴 44 ms 基线，说明没堵车；但 Reno 暴跌，CUBIC 因快速收敛机制被频繁误触发甚至比 Reno 更低；GLM-4-Flash 只调 7 次 API 就把吞吐提升 57%～58%，P95 尾时延也明显最低。")

    # ==================== SLIDE 8: EXP 2B RANDOM LOSS CWND & BETA ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "05  实验二：无线随机丢包（窗口与 β 演化）", "0.5% 与 1.0% 随机丢包下的 cwnd 曲线与 GLM-4-Flash 动态调参轨迹", 8)

    add_picture_fit(s, FIGDIR / "fig4_random_loss_cwnd_beta.png", 0.55, 1.28, 8.35, 5.72)

    add_card(s, 9.05, 1.38, 3.7, 2.55, "平均拥塞窗口显著抬升", [
        "0.5% 丢包：CUBIC 18.7、Reno 21.8 → GLM-4-Flash 33.4 MSS",
        "1.0% 丢包：CUBIC 12.9、Reno 16.0 → GLM-4-Flash 24.1 MSS",
        "橙线 CUBIC 长期处于最下方，紫线 GLM 整体高出一大截",
    ], accent=PURPLE, bg=TINT_PURPLE, body_size=11.8)

    add_card(s, 9.05, 4.12, 3.7, 2.78, "AI 动态调参过程稳定可查", [
        "第 5 s 首次评估即识别“队列空+持续重传”，上调至 β = 0.8",
        "全部 6 次仿真共 42 次调用中 41 次稳定输出 β = 0.8（仅 1 次 0.7）",
        "整个 55 s 运行仅需 7 次调用，全程无误判回调",
    ], accent=BLUE, bg=TINT_BLUE, body_size=11.8)

    set_notes(s, "这一页把 0.5% 和 1.0% 两种丢包率下的拥塞窗口曲线以及 GLM-4-Flash 的 β 轨迹放在一起看。很直观地看到：GLM 第 5 秒切到 0.8 后全程稳定保持，把平均窗口抬高超过五成，6 次仿真 42 次调用里 41 次稳定选出 0.8。")

    # ==================== SLIDE 9: EXP 3A FIXED BETA CALIBRATION & AI MATCH ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "06  实验三（上）：三档带宽的固定 β 标定与 AI 匹配论证", "14 → 40 → 3 Mbit/s 理论最优 β 为 0.5 → 0.7 → 0.4，GLM-4-Flash 逐段精准吻合", 9)

    add_picture_fit(s, FIGDIR / "fig5_capacity_change.png", 0.55, 1.32, 12.2, 4.18)

    add_card(s, 0.6, 5.58, 5.85, 1.38, "三档纯带宽的评判标准与预期调节倾向", [
        "14M（1×BDP）：β≥0.5 均跑满 13.50M，核心看 RTT → 最优 0.5（72 ms）",
        "40M（浅缓冲）看吞吐 → 最优 0.7（38.38M）；3M（吞吐全 2.89M）看 RTT → 最优 0.4（200 ms）",
    ], accent=BLUE, bg=TINT_BLUE, title_size=12.8, body_size=11.3)

    add_card(s, 6.85, 5.58, 5.88, 1.38, "GLM-4-Flash 精准贴合三段理论最优标尺", [
        "三次重复均稳定切出 0.5 → 0.7 → 0.4，三段主指标精确追平对应最优固定 β",
        "单一固定 β（含折中 0.6）无法兼顾：0.6 在 40M 少 1.06M 且在 3M RTT 多 16 ms",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=12.8, body_size=11.3)

    set_notes(s, "实验三先做固定 β 标定来论证 AI 调节逻辑：在 14 → 40 → 3 Mbit/s 三档纯带宽下，三段理论最优 β 恰好是 0.5、0.7 和 0.4，任何单一固定 β 都顾此失彼；而 GLM-4-Flash 三次重复全部精准切出 0.5 → 0.7 → 0.4，三段核心指标完全追平对应最优固定档。")

    # ==================== SLIDE 10: EXP 3B AI VS RENO & CUBIC ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "06  实验三（下）：AI 策略与传统算法（Reno、CUBIC）对比", "三档带宽切换下，GLM-4-Flash 兼得高速高吞吐与中低速低排队时延", 10)

    add_picture_fit(s, FIGDIR / "fig6_fixed_beta_tradeoff.png", 0.55, 1.28, 8.35, 5.72)

    add_card(s, 9.05, 1.38, 3.7, 2.55, "对比 Reno（固定 0.5）", [
        "14M 常规段：同按 0.5 运行，13.50M / 72 ms 完全持平",
        "40M 浅缓冲：GLM 切至 0.7 达 38.38M，较 Reno（35.48M）高 +2.90M（+8.2%）",
        "3M 拥塞段：GLM 切至 0.4 降至 200 ms，较 Reno（216 ms）再低 16 ms",
    ], accent=BLUE, bg=TINT_BLUE, body_size=11.4)

    add_card(s, 9.05, 4.12, 3.7, 2.78, "对比 CUBIC（固定 0.7）与丢包拆解", [
        "14M 常规段：均跑满 13.50M，GLM RTT 低 10 ms（72 vs 82 ms）",
        "40M 浅缓冲：吞吐持平（38.38 vs 38.48M），RTT 更低（51 vs 53 ms）",
        "3M 拥塞段：RTT 低 24 ms（200 vs 224 ms），稳态丢包 3 包少于 CUBIC 12 包",
        "全程丢包 0.314% 高于 CUBIC 源于 0–5 s HyStart 差异（5–82 s 运行期 292 < 311 包）",
    ], accent=PURPLE, bg=TINT_PURPLE, body_size=11.1)

    set_notes(s, "标定完预期后再把 GLM-4-Flash 和传统算法 Reno、CUBIC 直接对比。可以看到 GLM 在 14M 常规段中位 RTT 比 CUBIC 低 10 ms、40M 浅缓冲段吞吐比 Reno 高 2.9 Mbit/s 且追平 CUBIC、3M 拥塞段中位 RTT 比 CUBIC 低 24 ms 且比 Reno 低 16 ms。")

    # ==================== SLIDE 11: EXP 4 DELAY SHIFT ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "07  实验四：传播时延增加下的自适应吞吐对比", "路径变长致 RTT 翻倍时，AI 识破非拥塞稳定切至 0.7，吞吐 18.97 Mbit/s 略超 CUBIC", 11)

    add_picture_fit(s, FIGDIR / "fig7_delay_shift.png", 0.55, 1.30, 12.2, 4.22)

    add_card(s, 0.6, 5.60, 5.85, 1.35, "误判拥塞与固定折半均造成吞吐明显下滑", [
        "25 s 传播时延 20→40 ms，BDP 翻倍至 210 KB，55 KB 队列沦为 0.26 BDP 浅缓冲",
        "误判拥塞（固定 0.4）跌至 16.52 Mbit/s；Reno（0.5）排空缓冲跌至 17.24 Mbit/s",
    ], accent=BLUE, bg=TINT_BLUE, title_size=12.8, body_size=11.4)

    add_card(s, 6.85, 5.60, 5.88, 1.35, "GLM-4-Flash 纯数值识破非拥塞与客观局限", [
        "跳变前稳守 0.5（RTT 低 CUBIC 8 ms）；跳变后切至 0.7 达 18.97 Mbit/s，丢包率四组最低",
        "局限：25–31 s 存在约 6 s 过渡识别期，切至 0.7 后跳变后 RTT 高于 Reno 6 ms",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=12.8, body_size=11.4)

    set_notes(s, "实验四测试路由切换导致传播时延 20 变 40 ms。如果误判为拥塞降到 0.4 吞吐跌到 16.52 Mbit/s，Reno 折半跌到 17.24 Mbit/s；GLM-4-Flash 直接基于纯数值特征，跳变前稳守 0.5（RTT 比 CUBIC 低 8 ms），跳变后识破路径变长一次切至 0.7，三次重复稳定达到 18.97 Mbit/s（略高于 CUBIC 18.89 且丢包率低 28.3%）。")

    # ==================== SLIDE 12: EXP 5 FAIRNESS ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "08  实验五：三流共享瓶颈下的稳态公平性对比", "同构与异构六组同口径对照：AI 同构公平低时延，对存量 Reno 友好度显著优于 CUBIC", 12)

    add_picture_fit(s, FIGDIR / "fig8_fairness.png", 0.55, 1.32, 12.2, 4.15)

    add_card(s, 0.6, 5.56, 3.85, 1.40, "同构竞争：高公平且最低时延", [
        "3×GLM Jain 0.9940（与 3×Reno 持平）",
        "中位 RTT 74.0 ms，比 3×CUBIC 低 9.3 ms",
    ], accent=GREEN, bg=TINT_GREEN, title_size=12.8, body_size=11.4)

    add_card(s, 4.74, 5.56, 3.85, 1.40, "异构 TCP 友好性显著优于 CUBIC", [
        "2×Reno+GLM：Jain 0.9966，RTT 73.7 ms",
        "2×Reno+CUBIC：CUBIC 占 40.3%，Jain 跌至 0.9740",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=12.8, body_size=11.4)

    add_card(s, 8.88, 5.56, 3.85, 1.40, "三方混战与 AI 策略局限", [
        "混战 Jain 0.9868 高于 2×Reno+CUBIC（0.9740）",
        "局限：温和策略面对 CUBIC 偏弱，多流调用线性增",
    ], accent=ORANGE, bg=TINT_AMBER, title_size=12.8, body_size=11.4)

    set_notes(s, "实验五补齐了同构三组和异构三组共六组同口径对照。同构里 3×GLM 公平性与 3×Reno 持平（0.9940）且 RTT 为三组最低（74.0 ms，比 3×CUBIC 低 9.3 ms）；异构里 2×Reno+GLM 的公平性（0.9966）和时延（73.7 ms）都显著优于 2×Reno+CUBIC（0.9740 / 78.0 ms）；三方混战（0.9868）份额失衡源于 CUBIC 抢占 38.1%，也体现了温和友好与抗抢占的取舍。")

    # ==================== SLIDE 13: FEASIBILITY & CONCLUSION ====================
    s = prs.slides.add_slide(blank)
    set_bg(s, LIGHT_BG)
    add_header(s, "09  可行性分析与全文总结", "“AI 替代固定 AIMD 参数”可行有效，需注意周期解耦", 13)

    add_card(s, 0.6, 1.38, 5.85, 2.38, "一、效果与可解释性：切实可行", [
        "无线随机丢包：吞吐较 Reno +57%～58%、较 CUBIC +81%～90%",
        "带宽三档变化（14→40→3M）：匹配 0.5→0.7→0.4；时延翻倍 18.97M 略超 CUBIC",
        "多流同构 0.9940 最低时延，对存量 Reno 友好度（0.9966）显著优于 CUBIC（0.9740）",
    ], accent=GREEN, bg=TINT_GREEN, title_size=14, body_size=11.6)

    add_card(s, 6.85, 1.38, 5.88, 2.38, "二、调用开销实测与端侧部署可行性（222 次调用）", [
        "云端 GLM-4-Flash 中位耗时 2.24 s（P95 4.05 s）：定期评估+突变触发，单流平均 8.2 次",
        "多条 AI 流并发时云端总调用量线性增加（3 流共 21 次），高并发更宜端侧部署",
        "免费轻量模型直接读纯数值即取得明显收益，下沉端侧省去远程往返后可行性更高",
    ], accent=PURPLE, bg=TINT_PURPLE, title_size=13.5, body_size=11.8)

    add_card(s, 0.6, 4.00, 12.13, 1.82, "三、总体结论与后续改进方向", [
        "总体结论：“AI 替代固定 AIMD 参数”效果显著且工程可行；定期异步调用可有效控制云端开销，下沉至端侧本地部署则可进一步提高实时性",
        "后续改进：可在 Linux 网络命名空间 + tc 真实内核环境中验证后台异步调参，并探索端侧本地部署以进一步缩短切换响应时间",
    ], accent=NAVY, bg=TINT_BLUE, title_size=14, body_size=12.2)

    add_banner(
        s, 0.6, 6.08, 12.13, 0.78,
        "汇报完毕，感谢各位老师与同学的聆听！欢迎提问与指正",
        bg=NAVY, color=WHITE, size=15.5,
    )

    set_notes(s, "最后总结可行性：从效果看，AI 动态调参在随机丢包、带宽变化和时延变化中都有明显收益，多流竞争同构公平低时延且对存量 Reno 友好度优于 CUBIC；从开销看，21 次含 AI 仿真共 222 次调用，单条 AI 流平均仅需 8.2 次、中位耗时 2.24 秒，多流并发场景下下沉至端侧本地部署省去远程往返后可行性更高。谢谢各位老师！")

    prs.save(str(OUT_PPT))
    print(f"Saved {OUT_PPT} ({OUT_PPT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
