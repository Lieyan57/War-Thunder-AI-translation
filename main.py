import json,requests,re,time,threading
import tkinter as tk
import win32gui
import win32con
from pynput import keyboard
from openai import OpenAI
import os
import sys

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
messages = [{"role": "system", "content": config['SYSTEM_PROMPT']}]  # 全局对话历史
chat_log = []  # 历史记录
message_queue = []  # 消息队列
last_id = None
last_time = None
visible = True

def clear_context():                            #重置
    global messages, chat_log, message_queue, last_id, last_time
    messages = [{"role": "system", "content": config['SYSTEM_PROMPT']}]
    chat_log = []
    message_queue = []
    last_id = None
    last_time = None
    print("对话上下文已清空")

def fetch_messages(window, status_label):       #游戏消息队列
    global last_id, last_time, message_queue
    while True:
        try:
            r = connect(url)
            if r:
                rid = int(r['id'])
                rtime = r['time']
                if last_time is not None and rtime < last_time:
                    # 会话重置
                    clear_context()
                    window.after(0, lambda: status_label.config(text="检测到对话重置，已清空上下文"))
                    continue
                if last_id is None or rid > last_id:
                    original_msg = r["msg"]
                    if original_msg.strip() == "/clear":
                        clear_context()
                        window.after(0, lambda: status_label.config(text="上下文已清空"))
                        continue
                    if not is_chinese_text(original_msg):
                        # 添加到队列，按id排序
                        message_queue.append({"id": rid, "msg": original_msg, "time": rtime})
                        message_queue.sort(key=lambda x: x["id"])
                    last_id = rid
                    last_time = rtime
        except:
            time.sleep(0.1)  # 避免过于频繁请求
            pass
        
def translate_messages(window, status_label, history_widget):
    global message_queue
    while True:
        if message_queue:
            # 取最小id的消息
            msg_item = message_queue.pop(0)
            original_msg = msg_item["msg"]
            translated_msg = translate_to_chinese(original_msg)
            append_chat_log(original_msg, translated_msg, msg_item["time"])
            window.after(0, lambda: status_label.config(text="已翻译最新消息"))
            window.after(0, lambda: update_history_text(history_widget))
        time.sleep(0.05)

def append_chat_log(original, translated, time_val):
    global chat_log
    chat_log.append({"original": original, "translated": translated, "time": time_val})
    if len(chat_log) > config['HISTORY_MAX']:
        chat_log.pop(0)


def get_history_text():
    if not chat_log:
        return "等待翻译..."
    lines = []
    for item in chat_log:
        minutes = item["time"] // 60
        seconds = item["time"] % 60
        time_str = f"{minutes:02d}:{seconds:02d}"
        lines.append(f"[{time_str}] 原文: {item['original']}\n翻译: {item['translated']}")
    return "\n\n".join(lines)

def toggle_window():
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
    toggle_key = getattr(keyboard.Key, config['TOGGLE_KEY'].lower(), None)
    if toggle_key and key == toggle_key:
        toggle_window()

def is_chinese_text(text):
    text = text.strip()
    if not text:
        return False
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def translate_to_chinese(text): #ai翻译
    global messages
    messages.append({"role": "user", "content": config['TRANSLATE_PROMPT'].format(text=text)})
    response = client.chat.completions.create(
        model=config['MODEL'],
        messages=messages
    )
    translated = response.choices[0].message.content
    messages.append({"role": "assistant", "content": translated})

    return translated

def connect(url):  
    response = requests.get(url)
    if response.status_code == 200:
        try:
            data = re.findall(r'\{.*?\}', response.text)
            result_dict = json.loads(data[-1],strict=False)
        except:
             pass
    else:
        print("连接失败，请检查游戏运行情况")

    return result_dict

def update_history_text(widget):
    widget.config(state=tk.NORMAL)
    widget.delete("1.0", tk.END)
    widget.insert(tk.END, get_history_text())
    widget.config(state=tk.DISABLED)
    widget.see(tk.END)

if __name__ == "__main__":
    try:
        window = tk.Tk()
        window.title("翻译窗口")
        window.geometry(config['WINDOW_GEOMETRY'])  # 位置和大小
        window.attributes("-alpha", config['WINDOW_ALPHA'])  # 透明度
        window.attributes("-topmost", True)  # 总在前
        window.overrideredirect(True)  # 无边框

        # 设置点击穿透
        hwnd = window.winfo_id()
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TRANSPARENT)

        status_label = tk.Label(window, text="等待翻译...", font=("Arial", 12), bg="white", fg="black", anchor="w", justify="left")
        status_label.pack(fill=tk.X)

        history_text = tk.Text(window, font=("Arial", 11), bg="white", fg="black", wrap="word", state=tk.DISABLED)
        history_text.pack(expand=True, fill=tk.BOTH)
        update_history_text(history_text)

        # 启动获取消息线程
        threading.Thread(target=fetch_messages, args=(window, status_label), daemon=True).start()

        # 启动翻译线程
        threading.Thread(target=translate_messages, args=(window, status_label, history_text), daemon=True).start()

        # 启动键盘监听
        listener = keyboard.Listener(on_press=on_press)
        listener.start()

        window.mainloop()
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        input("按任意键退出...")