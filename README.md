# 悬浮语音输入 / Floating Voice Input

一个常驻 Windows 桌面的语音转文字悬浮球。点一下开始说话，再点一下结束，识别结果出现在按钮上方的面板里，右侧一键复制。

识别全程在本地运行，基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，**语音不会上传到任何服务器**。

## 特性

- 常驻桌面的悬浮球，可自由拖动，永远置顶
- 抗锯齿图标 + 动画：待机缓慢呼吸，录音时外圈随麦克风音量实时跳动，识别时转圈
- 可收起成一颗背景全透明的悬浮小球，收起后依然能录音
- 点击或全局快捷键 `Ctrl + Alt + 空格` 触发录音
- 结果面板可直接编辑，识别有误可当场改完再复制
- 识别完成自动复制到剪贴板，可关闭
- 完全离线，无需 API Key，无需联网（首次下载模型除外）
- 中文优化：强制简体输出、自动标点、支持中英混输

## 安装

需要 Python 3.10 或更高版本，安装时记得勾选 `Add Python to PATH`。

```bash
pip install -r requirements.txt
```

然后双击 `启动.bat`，或者：

```bash
python voice_widget.py
```

首次启动会自动下载语音模型（small 约 500MB），之后每次启动只需几秒。

## 使用

| 操作 | 说明 |
|---|---|
| 点击蓝色话筒球 | 开始录音，球变红 |
| 再点一次 | 结束录音，开始识别 |
| `Ctrl + Alt + 空格` | 全局快捷键，效果同上 |
| 「复制」按钮 | 复制面板内全部文字 |
| 「清空」按钮 | 清掉内容，准备下一段 |
| 右上角 — | 收起成小球 |
| 右上角 ✕ | 退出 |
| 拖动小球或底部条 | 移动位置 |
| 右键小球 | 菜单：展开 / 收起 / 退出 |

### 收起模式

点右上角的 `—`，整条工具栏会收起来，桌面上只剩一颗小球，背景是全透明的，不带黑框。

收起后小球照常工作：点一下开始录音，再点一下结束。**识别完成会自动展开**把文字给你看，复制完可以再收起去。

想手动展开或者退出，在小球上点右键。

把配置里的 `START_MINIMIZED` 改成 `True`，程序启动时就直接是小球状态。

连续录制多段会自动往下续行，可以一次性复制走。

## 配置

打开 `voice_widget.py`，最上方的配置区：

```python
MODEL_SIZE = "small"      # tiny / base / small / medium / large-v3
LANGUAGE = "zh"           # "zh" 中文，"en" 英文，None 自动判断
AUTO_COPY = True          # 识别完是否自动复制
HOTKEY = "ctrl+alt+space" # 全局快捷键
SUPERSAMPLE = 4           # 图标抗锯齿倍率，觉得不够细腻可调到 5 或 6
MIC_SENSITIVITY = 12.0    # 录音时外圈跳动的灵敏度
START_MINIMIZED = False   # 启动时是否直接收成小球
```

模型大小取舍：

| 值 | 体积 | 速度 | 中文准确度 |
|---|---|---|---|
| `base` | ~150MB | 很快 | 一般 |
| `small` | ~500MB | 适中 | 够用（默认） |
| `medium` | ~1.5GB | 偏慢 | 好 |
| `large-v3` | ~3GB | 慢 | 最好 |

## 常见问题

**悬浮球一直是灰的，显示「加载失败」**
模型下载被网络中断了，关掉重开会续下。反复失败可以先把 `MODEL_SIZE` 改成 `base` 试试。

**显示「麦克风打不开」**
Windows 设置 → 隐私和安全性 → 麦克风，确认「允许桌面应用访问麦克风」已开启。

**双击 .bat 一闪而过**
把 `启动.bat` 里的 `pythonw` 改成 `python`，重新双击，黑窗口会保留，可以看到具体报错。

**开机自启动**
`Win + R` 输入 `shell:startup`，把 `启动.bat` 的快捷方式拖进去。配合 `START_MINIMIZED = True` 使用体验更好。

**小球周围有一圈黑边**
透明抠图用的是 Windows 的颜色键，属于正常的边缘残留。如果特别明显，可能是 `TRANS_KEY` 和你的主题色撞了，换成别的冷门颜色即可。

**收起后找不到小球了**
它可能被拖到了屏幕边缘。关掉程序重开，会回到右下角默认位置。

## 依赖

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — 语音识别
- [sounddevice](https://python-sounddevice.readthedocs.io/) — 录音
- [Pillow](https://python-pillow.org/) — 图标抗锯齿绘制
- [keyboard](https://github.com/boppreh/keyboard) — 全局快捷键（可选）
- tkinter — 界面（Python 自带）

## 许可

MIT
