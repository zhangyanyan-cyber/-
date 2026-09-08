# -*- coding: utf-8 -*-
"""
桌面悬浮语音转文字小工具（Windows）

用法：点击悬浮球开始录音，再点一次停止。
识别结果出现在按钮上方的面板里，右侧「复制」按钮一键复制。
面板里的文字可以直接编辑修改后再复制。

依赖：pip install faster-whisper sounddevice numpy pillow
可选：pip install keyboard   （装了就支持全局快捷键 Ctrl+Alt+空格）
"""

import math
import threading
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ============ 配置区（想改就改这里） ============

MODEL_SIZE = "small"      # tiny / base / small / medium / large-v3
                          # 中文建议 small 起步；机器好可以换 medium，更准但更慢
LANGUAGE = "zh"           # 识别语言。"zh"=中文，"en"=英文，None=自动判断
AUTO_COPY = True          # 识别完是否自动复制到剪贴板
HOTKEY = "ctrl+alt+space" # 全局快捷键（需要装 keyboard 库，装不上也不影响用）

WIDTH = 400               # 窗口宽度
ICON_PX = 56              # 悬浮球显示尺寸
BAR_H = 66                # 底部按钮条高度
PANEL_H = 190             # 上方文字面板高度

SUPERSAMPLE = 4           # 抗锯齿倍率。图标还是不够细腻可以调到 5 或 6
MIC_SENSITIVITY = 12.0    # 录音时外圈跳动的灵敏度，觉得不明显就调大
START_MINIMIZED = False   # 启动时是否直接收成小球

# 让 Whisper 输出简体中文并自动加标点的小技巧
INIT_PROMPT = "以下是普通话的句子，请加上适当的标点符号。"

# ============ 配色 ============

BG = "#1e1f22"
PANEL_BG = "#26282c"
# 这个颜色会被 Windows 抠成全透明，收起成小球时当背景用。
# 它必须是界面上不会出现的颜色，一般不用改。
TRANS_KEY = "#010203"
TEXT_FG = "#e8e8ea"
MUTED = "#8b8f96"
ACCENT = "#4c8dff"
REC_COLOR = "#ff5c5c"
PROC_COLOR = "#f5a623"
OK_COLOR = "#4ac26b"

# 每个状态的球体渐变（上浅下深）
DISC_COLORS = {
    "loading": ((0x60, 0x64, 0x6b), (0x42, 0x45, 0x4b)),
    "idle":    ((0x6f, 0xa6, 0xff), (0x35, 0x71, 0xe8)),
    "recording": ((0xff, 0x82, 0x82), (0xe8, 0x3f, 0x3f)),
    "working": ((0xff, 0xc0, 0x5c), (0xe2, 0x92, 0x0d)),
}

SAMPLE_RATE = 16000
UI_FONT = ("Microsoft YaHei UI", 10)
SMALL_FONT = ("Microsoft YaHei UI", 8)

MINI_SIZE = ICON_PX + 10  # 收起后的窗口边长

IDLE_FRAMES = 24          # 呼吸动画帧数
LEVEL_STEPS = 14          # 音量环分几档
SPIN_FRAMES = 24          # 旋转动画帧数


# ============================================================
#  图标绘制：4 倍超采样 + LANCZOS 缩小 = 平滑边缘
# ============================================================

class IconFactory:
    """把图标画在放大 N 倍的画布上再缩小，以此得到抗锯齿效果。"""

    def __init__(self, px, ss, bg_hex=BG):
        self.px = px
        self.S = px * ss
        self._grad_cache = {}
        self.bg_rgb = tuple(int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))

    def _vgrad(self, top, bottom):
        """竖直渐变，缓存起来避免重复计算。"""
        key = (top, bottom)
        if key in self._grad_cache:
            return self._grad_cache[key]
        S = self.S
        strip = Image.new("RGB", (1, S))
        px = strip.load()
        for y in range(S):
            t = y / max(1, S - 1)
            px[0, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
        grad = strip.resize((S, S), Image.BILINEAR).convert("RGBA")
        self._grad_cache[key] = grad
        return grad

    def _mic(self, d, c, u):
        """话筒图形。u 是单位长度，方便按比例缩放。"""
        w = u * 0.020
        d.rounded_rectangle(
            [c - u * 0.048, c - u * 0.120, c + u * 0.048, c + u * 0.030],
            radius=u * 0.048, fill="white",
        )
        d.arc([c - u * 0.090, c - u * 0.082, c + u * 0.090, c + u * 0.082],
              start=0, end=180, fill="white", width=int(w))
        d.line([c, c + u * 0.082, c, c + u * 0.130], fill="white", width=int(w))
        d.line([c - u * 0.058, c + u * 0.132, c + u * 0.058, c + u * 0.132],
               fill="white", width=int(w))

    def _stop(self, d, c, u):
        """停止方块。"""
        d.rounded_rectangle(
            [c - u * 0.072, c - u * 0.072, c + u * 0.072, c + u * 0.072],
            radius=u * 0.022, fill="white",
        )

    def frame(self, state, halo=0.0, ring=0.0, spin=None, glyph="mic",
              blur=True):
        S = self.S
        c = S / 2
        disc_r = S * 0.325
        top, bottom = DISC_COLORS[state]

        # --- 光晕层（会被模糊）---
        soft = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        sd = ImageDraw.Draw(soft)

        if halo > 0:
            hr = disc_r * (1.0 + 0.40 * halo)
            sd.ellipse([c - hr, c - hr, c + hr, c + hr],
                       fill=(*bottom, int(75 * halo)))

        if ring > 0:
            rr = disc_r * (1.12 + 0.60 * ring)
            alpha = int(80 + 140 * ring) if blur else int(150 + 105 * ring)
            sd.ellipse([c - rr, c - rr, c + rr, c + rr],
                       outline=(*top, alpha),
                       width=max(2, int(S * 0.014)))

        if blur:
            soft = soft.filter(ImageFilter.GaussianBlur(S * 0.010))

        # --- 球体本身（不模糊，保持锐利）---
        disc = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).ellipse(
            [c - disc_r, c - disc_r, c + disc_r, c + disc_r], fill=255)
        disc.paste(self._vgrad(top, bottom), (0, 0), mask)

        canvas = Image.alpha_composite(soft, disc)
        d = ImageDraw.Draw(canvas)

        # --- 图形符号 ---
        if glyph == "stop":
            self._stop(d, c, S)
        elif glyph == "mic":
            self._mic(d, c, S)

        # --- 旋转指示器 ---
        if spin is not None:
            sr = disc_r * 1.30
            d.arc([c - sr, c - sr, c + sr, c + sr],
                  start=spin, end=spin + 95,
                  fill=(*top, 230), width=max(2, int(S * 0.022)))

        # 合到不透明背景上，再缩小
        out = Image.new("RGB", (S, S), self.bg_rgb)
        out.paste(canvas, (0, 0), canvas)
        return ImageTk.PhotoImage(
            out.resize((self.px, self.px), Image.LANCZOS))


# ============================================================
#  主程序
# ============================================================

class VoiceWidget:
    def __init__(self):
        self.state = "loading"      # loading / idle / recording / working
        self.model = None
        self.frames = []
        self.stream = None
        self.rec_seconds = 0
        self.panel_open = False

        self.level = 0.0            # 麦克风瞬时音量
        self.level_smooth = 0.0     # 平滑后的音量，给动画用
        self.anim_i = 0
        self.mini = False           # 是否收起成小球
        self.icons_mini = None

        self.root = tk.Tk()
        self.root.title("语音转文字")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        try:
            # Windows 专有：把这个颜色的像素抠成全透明，小球才不会顶着黑方块
            self.root.attributes("-transparentcolor", TRANS_KEY)
        except tk.TclError:
            pass

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.pos_x = sw - WIDTH - 40
        self.pos_bottom = sh - 80

        self._build_panel()
        self._build_bar()
        self._apply_geometry()

        self.root.bind("<Escape>", lambda e: self.quit())

        if HAS_PIL:
            self._build_icon_cache()
        self._build_menu()
        self._animate()

        if START_MINIMIZED:
            self.root.after(100, self.collapse)

        threading.Thread(target=self._load_model, daemon=True).start()
        self._try_bind_hotkey()

    # ---------- 图标缓存 ----------

    def _icon_set(self, bg_hex, glow=True):
        """按指定底色画出全套动画帧。

        展开态在深灰底上画，可以带柔和光晕；
        收起态要被抠成透明，光晕会在浅色桌面上糊出黑边，所以关掉光晕、
        改画清晰的实心环。
        """
        f = IconFactory(ICON_PX, SUPERSAMPLE, bg_hex)
        g = 1.0 if glow else 0.0
        b = glow

        def breathe(i):
            return g * (0.18 + 0.28 * (0.5 * (1 + math.sin(
                2 * math.pi * i / IDLE_FRAMES))))

        return {
            "idle": [
                f.frame("idle", halo=breathe(i), glyph="mic", blur=b)
                for i in range(IDLE_FRAMES)
            ],
            "recording": [
                f.frame("recording", halo=0.45 * g,
                        ring=i / (LEVEL_STEPS - 1), glyph="stop", blur=b)
                for i in range(LEVEL_STEPS)
            ],
            "working": [
                f.frame("working", halo=0.30 * g,
                        spin=i * (360 / SPIN_FRAMES), glyph="mic", blur=b)
                for i in range(SPIN_FRAMES)
            ],
            "loading": [
                f.frame("loading", spin=i * (360 / SPIN_FRAMES),
                        glyph="mic", blur=b)
                for i in range(SPIN_FRAMES)
            ],
        }

    def _build_icon_cache(self):
        """启动时把展开态的帧画好。收起态的那套等第一次最小化时再画。"""
        self.icons_normal = self._icon_set(BG)
        self.icons_mini = None

    # ---------- 动画主循环 ----------

    def _animate(self):
        if not HAS_PIL:
            self.root.after(200, self._animate)
            return

        self.anim_i += 1
        i = self.anim_i

        imgs = self.icons_mini if (self.mini and self.icons_mini) else self.icons_normal

        if self.state == "recording":
            # 音量平滑，避免图标抖得太厉害
            self.level_smooth += (self.level - self.level_smooth) * 0.35
            idx = int(min(1.0, self.level_smooth) * (LEVEL_STEPS - 1))
            img = imgs["recording"][idx]
        elif self.state == "working":
            img = imgs["working"][i % SPIN_FRAMES]
        elif self.state == "loading":
            img = imgs["loading"][i % SPIN_FRAMES]
        else:
            img = imgs["idle"][i % IDLE_FRAMES]

        self.icon.itemconfig(self.icon_item, image=img)
        self._current_img = img          # 防止被垃圾回收
        self.root.after(45, self._animate)

    # ---------- 界面搭建 ----------

    def _build_panel(self):
        """按钮上方的文字面板，右侧带复制按钮。"""
        self.panel = tk.Frame(self.root, bg=PANEL_BG, height=PANEL_H)

        side = tk.Frame(self.panel, bg=PANEL_BG, width=56)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)

        self.copy_btn = tk.Button(
            side, text="复制", font=UI_FONT, bg=ACCENT, fg="white",
            activebackground="#3d7ae8", activeforeground="white",
            relief="flat", bd=0, cursor="hand2", command=self.copy_text,
        )
        self.copy_btn.pack(fill="x", padx=6, pady=(8, 4), ipady=8)

        tk.Button(
            side, text="清空", font=SMALL_FONT, bg="#33363b", fg=MUTED,
            activebackground="#3c4046", activeforeground=TEXT_FG,
            relief="flat", bd=0, cursor="hand2", command=self.clear_text,
        ).pack(fill="x", padx=6, ipady=4)

        wrap = tk.Frame(self.panel, bg=PANEL_BG)
        wrap.pack(side="left", fill="both", expand=True)

        sb = tk.Scrollbar(wrap, width=8, troughcolor=PANEL_BG, bd=0,
                          highlightthickness=0, relief="flat")
        sb.pack(side="right", fill="y", pady=8)

        self.text = tk.Text(
            wrap, font=UI_FONT, bg=PANEL_BG, fg=TEXT_FG,
            insertbackground=TEXT_FG, selectbackground=ACCENT,
            relief="flat", bd=0, wrap="word", padx=12, pady=10,
            yscrollcommand=sb.set,
        )
        self.text.pack(fill="both", expand=True)
        sb.config(command=self.text.yview)

    def _build_bar(self):
        """底部：悬浮球 + 状态文字 + 关闭。整条都可以拖动。"""
        self.bar = tk.Frame(self.root, bg=BG, height=BAR_H)
        self.bar.pack(side="bottom", fill="x")
        self.bar.pack_propagate(False)

        self.icon = tk.Canvas(self.bar, width=ICON_PX, height=ICON_PX, bg=BG,
                              highlightthickness=0, cursor="hand2")
        self.icon.pack(side="left", padx=(8, 10), pady=5)
        self.icon_item = self.icon.create_image(ICON_PX // 2, ICON_PX // 2)
        # 小球既要能点击录音，又要能拖动窗口，靠移动距离来区分
        self.icon.bind("<Button-1>", self._icon_press)
        self.icon.bind("<B1-Motion>", self._icon_drag)
        self.icon.bind("<ButtonRelease-1>", self._icon_release)
        self.icon.bind("<Button-3>", self._popup_menu)

        self.status = tk.Label(self.bar, text="正在加载模型…", font=UI_FONT,
                               bg=BG, fg=MUTED, anchor="w")
        self.status.pack(side="left", fill="both", expand=True)

        self.close_btn = tk.Label(self.bar, text="✕", font=("Segoe UI", 12),
                                  bg=BG, fg=MUTED, cursor="hand2", padx=12)
        self.close_btn.pack(side="right", fill="y")
        self.close_btn.bind("<Button-1>", lambda e: self.quit())

        self.min_btn = tk.Label(self.bar, text="—", font=("Segoe UI", 12),
                                bg=BG, fg=MUTED, cursor="hand2", padx=10)
        self.min_btn.pack(side="right", fill="y")
        self.min_btn.bind("<Button-1>", lambda e: self.collapse())

        for w in (self.bar, self.status):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<Button-3>", self._popup_menu)

        if not HAS_PIL:
            self._draw_fallback("loading")

    def _draw_fallback(self, mode):
        """没装 Pillow 时的简易图标，能用但边缘会有锯齿。"""
        c = self.icon
        c.delete("all")
        color = {"loading": "#4a4d53", "idle": ACCENT,
                 "recording": REC_COLOR, "working": PROC_COLOR}[mode]
        p = ICON_PX
        c.create_oval(p * 0.14, p * 0.14, p * 0.86, p * 0.86,
                      fill=color, outline="")
        if mode == "recording":
            c.create_rectangle(p * 0.40, p * 0.40, p * 0.60, p * 0.60,
                               fill="white", outline="")
        else:
            c.create_oval(p * 0.42, p * 0.30, p * 0.58, p * 0.53,
                          fill="white", outline="")
            c.create_line(p * 0.50, p * 0.58, p * 0.50, p * 0.68,
                          fill="white", width=2)

    def _set_icon_state(self, mode):
        self.state = mode
        if not HAS_PIL:
            self._draw_fallback(mode)

    # ---------- 几何：面板从按钮「上方」展开 ----------

    def _apply_geometry(self):
        if self.mini:
            w = h = MINI_SIZE
        else:
            w = WIDTH
            h = BAR_H + (PANEL_H if self.panel_open else 0)
        self.root.geometry(f"{w}x{h}+{self.pos_x}+{self.pos_bottom - h}")

    def _open_panel(self):
        if not self.panel_open:
            self.panel_open = True
            self.panel.pack(side="top", fill="both", expand=True)
            self._apply_geometry()

    # ---------- 收起成小球 / 展开 ----------

    def collapse(self):
        """把整条工具栏收起来，只留一个悬浮小球。"""
        if self.mini:
            return
        if HAS_PIL and self.icons_mini is None:
            # 第一次收起时才渲染透明底的那套图，省启动时间
            self.icons_mini = self._icon_set(TRANS_KEY, glow=False)

        self.mini = True
        self.panel.pack_forget()
        self.status.pack_forget()
        self.min_btn.pack_forget()
        self.close_btn.pack_forget()

        self.root.configure(bg=TRANS_KEY)
        self.bar.configure(bg=TRANS_KEY, height=MINI_SIZE)
        self.icon.configure(bg=TRANS_KEY)
        self.icon.pack_configure(padx=5, pady=5)
        self._apply_geometry()

    def expand(self):
        """恢复成完整的工具栏。"""
        if not self.mini:
            return
        self.mini = False

        self.root.configure(bg=BG)
        self.bar.configure(bg=BG, height=BAR_H)
        self.icon.configure(bg=BG)
        self.icon.pack_configure(padx=(8, 10), pady=5)

        self.status.pack(side="left", fill="both", expand=True)
        self.close_btn.pack(side="right", fill="y")
        self.min_btn.pack(side="right", fill="y")
        if self.panel_open:
            self.panel.pack(side="top", fill="both", expand=True)
        self._apply_geometry()

    def _build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0, bg=PANEL_BG, fg=TEXT_FG,
                            activebackground=ACCENT, activeforeground="white",
                            bd=0, font=UI_FONT)

    def _popup_menu(self, e):
        self.menu.delete(0, "end")
        if self.mini:
            self.menu.add_command(label="展开", command=self.expand)
        else:
            self.menu.add_command(label="收起成小球", command=self.collapse)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit)
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    # ---------- 小球：区分「点击」和「拖动」 ----------

    def _icon_press(self, e):
        self._icon_moved = False
        self._drag_start(e)

    def _icon_drag(self, e):
        self._icon_moved = True
        self._drag_move(e)

    def _icon_release(self, e):
        if not self._icon_moved:
            self.toggle()

    def _drag_start(self, e):
        self._dx = e.x_root - self.pos_x
        self._dy = e.y_root - self.pos_bottom

    def _drag_move(self, e):
        self.pos_x = e.x_root - self._dx
        self.pos_bottom = e.y_root - self._dy
        self._apply_geometry()

    # ---------- 模型 ----------

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(MODEL_SIZE, device="cpu",
                                      compute_type="int8")
            self.root.after(0, self._model_ready)
        except Exception as exc:
            msg = str(exc)[:60]
            self.root.after(0, lambda: self._set_status(f"加载失败：{msg}", REC_COLOR))

    def _model_ready(self):
        self._set_icon_state("idle")
        self._set_status("点击话筒开始说话")

    def _set_status(self, text, color=MUTED):
        self.status.config(text=text, fg=color)

    # ---------- 录音 ----------

    def toggle(self):
        if self.state == "idle":
            self._start_recording()
        elif self.state == "recording":
            self._stop_recording()

    def _audio_cb(self, indata, n, t, s):
        import numpy as np
        self.frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata.astype("float64") ** 2)))
        self.level = min(1.0, rms * MIC_SENSITIVITY)

    def _start_recording(self):
        import sounddevice as sd

        self.frames = []
        self.level = self.level_smooth = 0.0
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                callback=self._audio_cb,
            )
            self.stream.start()
        except Exception as exc:
            self._set_status(f"麦克风打不开：{str(exc)[:40]}", REC_COLOR)
            return

        self._set_icon_state("recording")
        self.rec_seconds = 0
        self._tick()

    def _tick(self):
        if self.state != "recording":
            return
        m, s = divmod(self.rec_seconds, 60)
        self._set_status(f"录音中 {m:02d}:{s:02d}　（再点一次结束）", REC_COLOR)
        self.rec_seconds += 1
        self.root.after(1000, self._tick)

    def _stop_recording(self):
        import numpy as np

        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass

        self._set_icon_state("working")
        self._set_status("识别中…", PROC_COLOR)

        if not self.frames:
            self._model_ready()
            self._set_status("没录到声音，检查一下麦克风", REC_COLOR)
            return

        audio = np.concatenate(self.frames, axis=0).flatten()
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _transcribe(self, audio):
        try:
            segments, _ = self.model.transcribe(
                audio,
                language=LANGUAGE,
                beam_size=5,
                vad_filter=True,
                initial_prompt=INIT_PROMPT,
            )
            result = "".join(seg.text for seg in segments).strip()
        except Exception as exc:
            result = None
            err = str(exc)[:60]
            self.root.after(0, lambda: self._set_status(f"识别出错：{err}", REC_COLOR))

        if result is not None:
            self.root.after(0, lambda: self._show_result(result))
        else:
            self.root.after(0, self._model_ready)

    # ---------- 结果 ----------

    def _show_result(self, text):
        self.expand()          # 收起状态下出了结果，自动弹回来给你看
        self._open_panel()

        if not text:
            self._model_ready()
            self._set_status("没听清，再试一次", REC_COLOR)
            return

        existing = self.text.get("1.0", "end").strip()
        if existing:
            self.text.insert("end", "\n" + text)
        else:
            self.text.insert("1.0", text)
        self.text.see("end")

        self._set_icon_state("idle")

        if AUTO_COPY:
            self.copy_text()
        else:
            self._set_status("识别完成", OK_COLOR)

    def copy_text(self):
        content = self.text.get("1.0", "end").strip()
        if not content:
            self._set_status("还没有内容", MUTED)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self._set_status("已复制，去别的地方 Ctrl+V", OK_COLOR)
        self.root.after(2500, lambda: self._set_status("点击话筒开始说话")
                        if self.state == "idle" else None)

    def clear_text(self):
        self.text.delete("1.0", "end")
        self._set_status("已清空")

    # ---------- 全局快捷键（可选） ----------

    def _try_bind_hotkey(self):
        try:
            import keyboard
            keyboard.add_hotkey(HOTKEY, lambda: self.root.after(0, self.toggle))
        except Exception:
            pass

    # ---------- 运行 ----------

    def quit(self):
        try:
            if self.stream:
                self.stream.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    VoiceWidget().run()
