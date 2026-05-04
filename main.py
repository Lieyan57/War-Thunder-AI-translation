import requests,re,time,threading,json
import os,sys
import tkinter as tk
import tkinter.font as tkfont
import win32gui
import win32con
from pynput import keyboard
from openai import OpenAI

# 加载配置文件
try:
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(__file__)
    config_path = os.path.join(base_dir, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
except Exception as e:
    print(f"加载配置文件失败: {e}")
    input("按任意键退出...")
    exit(1)

# 设置 DeepSeek API
try:
    client = OpenAI(api_key=config['API_KEY'], base_url=config['BASE_URL'])
except Exception as e:
    print(f"初始化API客户端失败: {e}")
    input("按任意键退出...")
    exit(1)

url = "http://localhost:8111/gamechat?lastId=0"


ai_messge = [{"role": "system", "content": config['SYSTEM_PROMPT']}]  # 全局对话历史

last_id = 0
last_time = 0
old_msg = []
待处理消息 = []
chat_log = []       # 翻译历史记录
visible = True      # 窗口可见状态

def remove_zwsp(obj):
    #递归移除对象中所有字符串里的零宽空格 \u200b

    if isinstance(obj, dict):
        return {k: remove_zwsp(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [remove_zwsp(item) for item in obj]
    elif isinstance(obj, str):
        return obj.replace('\u200b', '')
    else:
        return obj

def connect(t_url):     #连接服务器
    try:
        resp = requests.get(t_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()  # 返回列表[dict]
            return remove_zwsp(data)
        else:
            return []
    except Exception as e:
        print(f"连接失败: {e}")
        print("等待游戏启动...")
        time.sleep(5)

def clear_chat():       #清除聊天记录
    global last_id, last_time, url, old_msg, ai_messge, chat_log, 待处理消息
    last_id = 0
    last_time = 0
    old_msg = []
    待处理消息 = []
    chat_log = []
    ai_messge = [{"role": "system", "content": config['SYSTEM_PROMPT']}]  # 重置对话历史
    print("聊天记录已清除")

def get_new_chat():     #获取聊天记录
    global last_id, last_time, url, old_msg, 待处理消息
    while True:
        try:
            now_msg = connect(url)
            if now_msg == [] and old_msg == []:
                print("等待对局开始...",end="\r")
                continue
            elif now_msg == [] and old_msg != []:
                print("对局已结束，等待下一局...")
                clear_chat()
                window.after(0, lambda: set_status_text("检测到对局结束，已清空上下文"))
                window.after(0, update_history_display)
                continue
            else:       #对比完整的聊天记录，剔除旧信息，返回完整的新信息列表
                new_msg = []
                old_msg_count = len(old_msg)
                now_msg_count = len(now_msg)
                if now_msg_count > old_msg_count:
                    for i in range(old_msg_count, now_msg_count):
                        new_msg.append(now_msg[i])
                        待处理消息.append(now_msg[i])
                        print("新消息:", now_msg[i])
                    old_msg = now_msg
                    last_id = now_msg[-1]['id']
                    last_time = now_msg[-1]['time']
                else:
                    pass

        except Exception as e:
            print("get_new_chat error:", e)

        time.sleep(0.5)

def 处理消息():
    global 待处理消息
    while True:
        if 待处理消息:
            msg_dict = 待处理消息.pop(0)
            msg = msg_dict['msg']
            msg_time = msg_dict.get('time', 0)
            print("处理消息:", msg)
            if re.search(r'[\u4e00-\u9fff]', str(msg)):
                pass
            else:
                fany_msg = ai_translate(msg)
                print("翻译结果:", fany_msg)
                append_chat_log(msg, fany_msg, msg_time)
                window.after(0, lambda: set_status_text("已翻译最新消息"))
                window.after(0, update_history_display)
        else:
            time.sleep(0.05)

def ai_translate(msg):
    global ai_messge
    ai_messge.append({"role": "user", "content": config['TRANSLATE_PROMPT'].format(text=msg)})
    resp = client.chat.completions.create(
        model=config['MODEL'],
        messages=ai_messge
    )
    fanyi = resp.choices[0].message.content
    ai_messge.append({"role": "assistant", "content": fanyi})
    return fanyi

# ========== UI 相关函数 ==========

def draw_outlined_text(canvas, x, y, text, fill, outline, font, anchor="nw"):
    # 绘制带描边的文字（4方向偏移 + 中心填充）

    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        canvas.create_text(x + dx, y + dy, text=text, fill=outline, font=font, anchor=anchor)
    canvas.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor)

def wrap_text(text, max_width, font):
    # 按像素宽度自动换行

    lines = []
    for paragraph in text.split('\n'):
        current = ""
        for ch in paragraph:
            test = current + ch
            if font.measure(test) > max_width:
                if current:
                    lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
    return lines

def set_status_text(text):
    # 更新状态栏文字
    
    status_canvas.delete("all")
    draw_outlined_text(status_canvas, 2, 2, text, fg_color, outline_color, font_large, "nw")

def update_history_display():
    # 在 Canvas 上重绘翻译历史（带滚动支持）
    
    history_canvas.delete("all")
    if not chat_log:
        draw_outlined_text(history_canvas, 2, 2, "等待聊天内容...", fg_color, outline_color, font_normal, "nw")
        history_canvas.config(scrollregion=(0, 0, 1, 1))
        return

    canvas_width = history_canvas.winfo_width()
    if canvas_width < 10:
        canvas_width = 400
    max_text_width = canvas_width - 6

    y = 2
    for item in chat_log:
        minutes = item["time"] // 60
        seconds = item["time"] % 60
        time_str = f"{minutes:02d}:{seconds:02d}"

        # 原文行
        orig_text = f"[{time_str}] 原文: {item['original']}"
        for line in wrap_text(orig_text, max_text_width, font_normal):
            draw_outlined_text(history_canvas, 2, y, line, fg_color, outline_color, font_normal, "nw")
            y += font_normal.metrics("linespace")
        y += 2  # 段落间距

        # 翻译行
        trans_text = f"翻译: {item['translated']}"
        for line in wrap_text(trans_text, max_text_width, font_normal):
            draw_outlined_text(history_canvas, 2, y, line, fg_color, outline_color, font_normal, "nw")
            y += font_normal.metrics("linespace")
        y += 2  # 两条消息间距

    history_canvas.config(scrollregion=(0, 0, canvas_width, y))
    history_canvas.yview_moveto(1.0)  # 滚动到底部

def on_mouse_wheel(event):
    #鼠标滚轮滚动

    history_canvas.yview_scroll(-1 * (event.delta // 120), "units")

def append_chat_log(original, translated, time_val):
    #添加翻译记录到历史

    global chat_log
    chat_log.append({"original": original, "translated": translated, "time": time_val})
    if len(chat_log) > config['HISTORY_MAX']:
        chat_log.pop(0)

def toggle_window():
    #切换窗口显示/隐藏，带点击穿透

    global visible
    visible = not visible
    if visible:
        window.deiconify()
        window.attributes("-topmost", True)
        hwnd = window.winfo_id()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TRANSPARENT)
    else:
        window.withdraw()

def on_press(key):
    #键盘按键回调

    toggle_key = getattr(keyboard.Key, config['TOGGLE_KEY'].lower(), None)
    if toggle_key and key == toggle_key:
        window.after(0, toggle_window)

if __name__ == "__main__":
    try:
        # ========== 创建穿透悬浮窗口（Canvas 绘制描边文字） ==========
        window = tk.Tk()
        window.title("翻译窗口")
        window.geometry(config['WINDOW_GEOMETRY'])
        window.configure(bg=config['TRANSPARENT_COLOR'])
        window.wm_attributes('-transparentcolor', config['TRANSPARENT_COLOR'])
        window.attributes("-topmost", True)
        window.overrideredirect(True)

        # 点击穿透
        hwnd = window.winfo_id()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TRANSPARENT)

        # 从配置读取样式（全局变量，供 UI 函数使用）
        bg_color = config['TRANSPARENT_COLOR']
        fg_color = config['TEXT_COLOR']
        outline_color = config['OUTLINE_COLOR']
        font_family = config['FONT_FAMILY']
        font_large = tkfont.Font(family=font_family, size=config['FONT_SIZE_LARGE'], weight="bold")
        font_normal = tkfont.Font(family=font_family, size=config['FONT_SIZE'], weight="bold")

        # 状态栏 Canvas
        status_canvas = tk.Canvas(
            window, bg=bg_color, highlightthickness=0, borderwidth=0,
            height=font_large.metrics("linespace") + 4
        )
        status_canvas.pack(fill=tk.X)
        set_status_text("等待聊天内容...")

        # 历史区域 Canvas（可滚动）
        history_canvas = tk.Canvas(
            window, bg=bg_color, highlightthickness=0, borderwidth=0
        )
        history_canvas.pack(expand=True, fill=tk.BOTH)
        update_history_display()

        # 绑定滚轮
        history_canvas.bind("<MouseWheel>", on_mouse_wheel)
        
        # Windows 触控板支持
        history_canvas.bind("<MouseWheel>", on_mouse_wheel)

        # 启动获取消息线程
        threading.Thread(target=get_new_chat, daemon=True).start()

        # 启动翻译线程
        threading.Thread(target=处理消息, daemon=True).start()

        # 启动键盘监听
        listener = keyboard.Listener(on_press=on_press)
        listener.start()

        window.mainloop()

    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        input("按任意键退出...")
