# main.py
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.dialog import MDDialog
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.utils import platform
import requests, re, time, threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Android
if platform == 'android':
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    activity = PythonActivity.mActivity
    PowerManager = autoclass('android.os.PowerManager')
    ConnectivityManager = autoclass('android.net.ConnectivityManager')

KV = '''
#:import dp kivy.metrics.dp

<SettingsScreen>:
    name: "settings"
    BoxLayout:
        orientation: "vertical"
        padding: dp(30)
        spacing: dp(15)
        MDLabel:
            text: "Settings"
            font_style: "H5"
            halign: "center"
            size_hint_y: None
            height: dp(60)
        MDTextField:
            id: token; hint_text: "GitHub Token"; password: True
        MDTextField:
            id: repo; hint_text: "username/repo"
        MDTextField:
            id: path; hint_text: "channels.m3u"; text: "channels.m3u"
        MDTextField:
            id: branch; hint_text: "main"; text: "main"
        MDTextField:
            id: interval; hint_text: "Auto-refresh (h)"; input_filter: "float"; text: "2.0"
        MDTextField:
            id: workers; hint_text: "Parallel"; input_filter: "int"; text: "15"
        MDRectangleFlatButton:
            text: "Save"
            on_release: root.save()

<MainScreen>:
    name: "main"
    BoxLayout:
        orientation: "vertical"
        padding: dp(30)
        spacing: dp(20)
        MDLabel:
            text: "Local ISP TV"
            font_style: "H4"
            size_hint_y: None
            height: dp(100)
        MDLabel:
            id: status
            text: "Ready"
        MDCard:
            size: dp(320), dp(90); pos_hint: {"center_x": .5}
            MDRectangleFlatButton:
                text: "Scrape & Upload"
                on_release: root.run()
        MDCard:
            size: dp(320), dp(90); pos_hint: {"center_x": .5}
            MDRectangleFlatButton:
                text: "Open in VLC"
                on_release: root.vlc()
        MDCard:
            size: dp(320), dp(90); pos_hint: {"center_x": .5}
            MDRectangleFlatButton:
                text: "Settings"
                on_release: app.open_settings()
        MDCard:
            size: dp(320), dp(90); pos_hint: {"center_x": .5}
            MDRectangleFlatButton:
                id: pause_btn
                text: "Pause Auto"
                on_release: root.toggle_pause()
        MDLabel:
            id: timer
            text: "Next: --:--:--"
'''

# Config
BASE_URL = "http://redforce.live/"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}
M3U_FILE = Path("/storage/emulated/0/Download/channels.m3u")
GITHUB_TOKEN = GITHUB_REPO = GITHUB_PATH = GITHUB_BRANCH = ""
AUTO_REFRESH_HOURS = 2.0
MAX_WORKERS = 15
AUTO_PAUSED = False

class SettingsScreen(Screen):
    def save(self):
        app = MDApp.get_running_app()
        t, r, p, b = self.ids.token.text.strip(), self.ids.repo.text.strip(), self.ids.path.text.strip(), self.ids.branch.text.strip()
        i = max(float(self.ids.interval.text or 2), 0.5)
        w = max(min(int(self.ids.workers.text or 15), 30), 5)
        err = []
        if not t or not app.validate_token(t): err.append("Invalid token")
        if not r or not re.match(r'^[\w-]+/[\w-]+$', r): err.append("Invalid repo")
        if not p or p.startswith('/') or '..' in p: err.append("Invalid path")
        if not b: err.append("Branch required")
        if err: return self.msg("\n".join(f"• {e}" for e in err), 1)
        app.store.put('github_token', value=t); app.store.put('github_repo', value=r)
        app.store.put('github_path', value=p); app.store.put('github_branch', value=b)
        app.store.put('interval', value=i); app.store.put('workers', value=w)
        global GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS
        GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS = t, r, p, b, i, w
        self.msg("Saved!", 0); app.sm.current = "main"; app.refresh()

    def validate_token(self, t): 
        try: 
            r = requests.get("https://api.github.com/user", headers={"Authorization": f"token {t}"}, timeout=8)
            return r.status_code == 200 and "repo" in r.headers.get("X-OAuth-Scopes", "")
        except: return False
    def msg(self, m, e=0): 
        if hasattr(self, 'msg_lbl'): self.remove_widget(self.msg_lbl)
        self.msg_lbl = MDLabel(text=m, text_color=(1,0.3,0.3,1) if e else (0.3,1,0.3,1), size_hint_y=None, height=dp(60), halign="center")
        self.add_widget(self.msg_lbl, index=1)

class MainScreen(Screen):
    def run(self):
        if platform == 'android' and not self.online(): return self.dlg("No Internet")
        self.ids.status.text = "Scraping..."
        self.wake_lock()
        threading.Thread(target=self.worker, daemon=True).start()
    def worker(self):
        try:
            total, ok = scrape()
            up = upload()
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', f"Done! {ok}/{total} | GitHub: {'OK' if up else 'Failed'}"))
        except Exception as e: Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', f"Error: {e}"))
        finally: self.release_wake_lock()
    def vlc(self):
        if not M3U_FILE.exists(): return self.dlg("No M3U", "Scrape first")
        if platform == 'android':
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            i = Intent(Intent.ACTION_VIEW)
            i.setDataAndType(Uri.fromFile(M3U_FILE), "audio/x-mpegurl")
            i.setPackage("org.videolan.vlc")
            activity.startActivity(i)
    def toggle_pause(self):
        global AUTO_PAUSED
        AUTO_PAUSED = not AUTO_PAUSED
        MDApp.get_running_app().store.put('paused', value=AUTO_PAUSED)
        self.ids.pause_btn.text = "Resume Auto" if AUTO_PAUSED else "Pause Auto"
        self.ids.pause_btn.md_bg_color = (0.8,0.3,0.3,1) if AUTO_PAUSED else (0.3,0.8,0.3,1)
        self.ids.timer.text = "Paused" if AUTO_PAUSED else "Next: --:--:--"
        if not AUTO_PAUSED: MDApp.get_running_app().refresh()
    def online(self):
        if platform != 'android': return True
        cm = activity.getSystemService(ConnectivityManager)
        n = cm.getActiveNetworkInfo()
        return n and n.isConnected()
    def wake_lock(self):
        if platform == 'android' and not hasattr(self, 'wl'):
            self.wl = activity.getSystemService(PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ISP")
            self.wl.acquire()
    def release_wake_lock(self):
        if platform == 'android' and hasattr(self, 'wl') and self.wl.isHeld(): self.wl.release()
    def dlg(self, t, m=""): MDDialog(title=t, text=m, size_hint=(0.8, 0.4)).open()

# Scrape
def scrape():
    s = requests.Session(); s.headers.update(HEADERS)
    soup = BeautifulSoup(s.get(BASE_URL, timeout=20).text, "lxml")
    items = [(i.find("img").get("alt","").strip(), [c for c in li.get("class",[]) if c!="All"], 
              re.search(r"stream=(\d+)", a.get("onclick","")).group(1), urljoin(BASE_URL, i.find("img").get("src","")))
             for li in soup.select("ul#vidlink li") if (a:=li.find("a", {"onclick":True}) and (i:=a.find("img")))]
    ids = [sid for _,_,sid,_ in items]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        urls = dict(ex.map(lambda sid: (sid, resolve(sid)), ids))
    resolved = [(n,c,sid,l,urls[sid]) for n,c,sid,l in items if urls.get(sid)]
    if resolved:
        M3U_FILE.parent.mkdir(exist_ok=True)
        M3U_FILE.write_text("\n".join(["#EXTM3U"] + [f'#EXTINF:-1 tvg-name="{n.replace('"',"'")}" tvg-logo="{l}" group-title="{c[0] if c else ""}",{n.replace('"',"'")}\n{u}' for n,c,_,l,u in resolved]))
    return len(items), len(resolved)

def resolve(sid):
    try:
        r = requests.get(urljoin(BASE_URL, f"player.php?stream={sid}"), headers=HEADERS, timeout=20)
        for p in [r'<iframe[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']', r'<source[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']', r'(https?://[^\s\'"]*\.m3u8[^\s\'"]*)']:
            if (m:=re.search(p, r.text, re.I)): return urljoin(r.url, m.group(1).strip())
        return r.url if ".m3u8" in r.url else None
    except: return None

def upload():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    h = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = requests.get(url, headers=h).json().get("sha") if requests.get(url, headers=h).ok else None
    data = {"message": f"Update {time.strftime('%H:%M')}", "content": requests.utils.quote(M3U_FILE.read_text()), "branch": GITHUB_BRANCH}
    if sha: data["sha"] = sha
    return requests.put(url, headers=h, json=data).ok

class LocalISPTVApp(MDApp):
    def build(self):
        self.title = "Local ISP TV"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.store = JsonStore('config.json')
        self.load()
        Builder.load_string(KV)
        self.sm = self.root
        self.sm.add_widget(MainScreen())
        self.sm.add_widget(SettingsScreen())
        self.sm.current = "main"
        if Window.width > 1000: Window.size = (1280, 720)
        self.refresh()
        return self.sm

    def load(self):
        global GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS, AUTO_PAUSED
        GITHUB_TOKEN = self.store.get('github_token')['value'] if self.store.exists('github_token') else ""
        GITHUB_REPO = self.store.get('github_repo')['value'] if self.store.exists('github_repo') else ""
        GITHUB_PATH = self.store.get('github_path')['value'] if self.store.exists('github_path') else "channels.m3u"
        GITHUB_BRANCH = self.store.get('github_branch')['value'] if self.store.exists('github_branch') else "main"
        AUTO_REFRESH_HOURS = float(self.store.get('interval')['value']) if self.store.exists('interval') else 2.0
        MAX_WORKERS = int(self.store.get('workers')['value']) if self.store.exists('workers') else 15
        AUTO_PAUSED = self.store.get('paused')['value'] if self.store.exists('paused') else False

    def open_settings(self):
        s = self.sm.get_screen("settings")
        for k in ['token','repo','path','branch','interval','workers']:
            s.ids[k].text = globals()[k.upper().replace('PATH','_PATH')] if 'PATH' in k else str(globals()[k.upper()])
        self.sm.current = "settings"

    def refresh(self):
        if hasattr(self, 'timer'): self.timer.cancel()
        if AUTO_PAUSED: 
            self.sm.get_screen("main").ids.timer.text = "Paused"
            return
        self.timer = Clock.schedule_once(self.auto, AUTO_REFRESH_HOURS * 3600)
        self.update_timer(AUTO_REFRESH_HOURS * 3600)

    def update_timer(self, sec):
        if AUTO_PAUSED: return
        h, m = divmod(int(sec)//60, 60)
        self.sm.get_screen("main").ids.timer.text = f"Next: {h:02d}:{m:02d}"
        Clock.schedule_once(lambda dt: self.update_timer(sec - 1), 1)

    def auto(self, dt):
        if not AUTO_PAUSED: self.sm.get_screen("main").run()
        self.refresh()

LocalISPTVApp().run()
