# main.py
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.utils import platform
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

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
            text: "GitHub & Performance"
            theme_text_color: "Primary"
            font_style: "H5"
            size_hint_y: None
            height: dp(70)
            halign: "center"

        MDTextField:
            id: token
            hint_text: "GitHub Token"
            password: True
            helper_text: "Must have 'repo' scope"
            helper_text_mode: "on_error"

        MDTextField:
            id: repo
            hint_text: "username/repo"
            helper_text: "e.g. john/tv"

        MDTextField:
            id: path
            hint_text: "channels.m3u"
            text: "channels.m3u"

        MDTextField:
            id: branch
            hint_text: "main"
            text: "main"

        MDTextField:
            id: interval
            hint_text: "Auto-refresh (hours)"
            input_filter: "float"
            text: "2.0"
            helper_text: "≥ 0.5"

        MDTextField:
            id: workers
            hint_text: "Parallel requests"
            input_filter: "int"
            text: "15"
            helper_text: "5–30"

        MDRectangleFlatButton:
            text: "Save Settings"
            on_release: root.save_settings()

<MainScreen>:
    name: "main"
    BoxLayout:
        orientation: "vertical"
        padding: dp(30)
        spacing: dp(20)

        MDLabel:
            id: title
            text: "Local ISP TV"
            font_style: "H4"
            size_hint_y: None
            height: dp(100)

        MDLabel:
            id: status
            text: "Ready"
            halign: "center"

        MDCard:
            size_hint: None, None
            size: dp(320), dp(90)
            pos_hint: {"center_x": .5}
            elevation: 12
            padding: dp(15)
            MDRectangleFlatButton:
                text: "Scrape & Upload"
                font_size: "24sp"
                on_release: root.scrape_and_upload()

        MDCard:
            size_hint: None, None
            size: dp(320), dp(90)
            pos_hint: {"center_x": .5}
            elevation: 12
            padding: dp(15)
            MDRectangleFlatButton:
                text: "Open in VLC"
                font_size: "24sp"
                on_release: root.open_in_vlc()

        MDCard:
            size_hint: None, None
            size: dp(320), dp(90)
            pos_hint: {"center_x": .5}
            elevation: 12
            padding: dp(15)
            MDRectangleFlatButton:
                text: "Settings"
                font_size: "24sp"
                on_release: app.open_settings()

        MDLabel:
            id: timer
            text: "Next: --:--:--"
            halign: "center"
'''

class SettingsScreen(Screen):
    def save_settings(self):
        app = MDApp.get_running_app()
        token = self.ids.token.text.strip()
        repo = self.ids.repo.text.strip()
        path = self.ids.path.text.strip()
        branch = self.ids.branch.text.strip()
        try: interval = max(float(self.ids.interval.text), 0.5)
        except: interval = 2.0
        try: workers = max(min(int(self.ids.workers.text), 30), 5)
        except: workers = 15

        errors = []
        if not token: errors.append("Token required")
        elif not self.validate_token(token): errors.append("Invalid token")
        if not repo or not re.match(r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$', repo): errors.append("Invalid repo")
        if not path or path.startswith('/') or '..' in path: errors.append("Invalid path")
        if not branch: errors.append("Branch required")

        if errors:
            self.show_msg("\n".join(f"• {e}" for e in errors), error=True)
            return

        app.store.put('github_token', value=token)
        app.store.put('github_repo', value=repo)
        app.store.put('github_path', value=path)
        app.store.put('github_branch', value=branch)
        app.store.put('interval', value=interval)
        app.store.put('workers', value=workers)

        global GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS
        GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS = (
            token, repo, path, branch, interval, workers
        )

        self.show_msg("Saved!", error=False)
        app.sm.current = "main"
        app.start_auto_refresh()

    def validate_token(self, token): 
        try:
            r = requests.get("https://api.github.com/user", headers={"Authorization": f"token {token}"}, timeout=8)
            return r.status_code == 200 and "repo" in r.headers.get("X-OAuth-Scopes", "")
        except: return False

    def show_msg(self, msg, error=False):
        if hasattr(self, 'msg'): self.remove_widget(self.msg)
        self.msg = MDLabel(text=msg, text_color=(1,0.3,0.3,1) if error else (0.3,1,0.3,1), size_hint_y=None, height=dp(60), halign="center")
        self.add_widget(self.msg, index=1)

class MainScreen(Screen):
    def scrape_and_upload(self):
        if platform == 'android' and not self.is_online():
            self.show_dialog("No Internet", "Connect to Wi-Fi")
            return
        self.ids.status.text = "Scraping..."
        self.acquire_wake_lock()
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            total, ok = scrape_and_save()
            success = upload_to_github()
            msg = f"Done! {ok}/{total} streams | GitHub: {'OK' if success else 'Failed'}"
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', msg))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', f"Error: {e}"))
        finally:
            self.release_wake_lock()

    def open_in_vlc(self):
        if not M3U_FILE.exists():
            self.show_dialog("No M3U", "Scrape first")
            return
        if platform == 'android':
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(Uri.fromFile(M3U_FILE), "audio/x-mpegurl")
            intent.setPackage("org.videolan.vlc")
            activity.startActivity(intent)

    def show_dialog(self, title, text):
        MDDialog(title=title, text=text, size_hint=(0.8, 0.4)).open()

    def is_online(self):
        if platform != 'android': return True
        cm = activity.getSystemService(ConnectivityManager)
        net = cm.getActiveNetworkInfo()
        return net is not None and net.isConnected()

    def acquire_wake_lock(self):
        if platform == 'android' and not hasattr(self, 'wake_lock'):
            self.wake_lock = activity.getSystemService(PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "LocalISP")
            self.wake_lock.acquire()

    def release_wake_lock(self):
        if platform == 'android' and hasattr(self, 'wake_lock') and self.wake_lock.isHeld():
            self.wake_lock.release()

# === SCRAPING ===
BASE_URL = "http://redforce.live/"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": BASE_URL}
M3U_FILE = Path("/storage/emulated/0/Download/channels.m3u")
GITHUB_TOKEN = GITHUB_REPO = GITHUB_PATH = GITHUB_BRANCH = ""
AUTO_REFRESH_HOURS = 2.0
MAX_WORKERS = 15

def scrape_and_save():
    s = requests.Session()
    s.headers.update(HEADERS)
    soup = BeautifulSoup(s.get(BASE_URL, headers=HEADERS, timeout=20).text, "lxml")
    raw = [(i.find("img").get("alt","").strip(), [c for c in li.get("class",[]) if c!="All"], re.search(r"stream=(\d+)", a.get("onclick","")).group(1), urljoin(BASE_URL, i.find("img").get("src",""))) 
           for li in soup.select("ul#vidlink li") if (a:=li.find("a", {"onclick":True}) and (i:=a.find("img")))]
    ids = [sid for _, _, sid, _ in raw]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        urls = dict(ex.map(lambda sid: (sid, resolve_url(sid)), ids))
    resolved = [(n,c,sid,l,urls[sid]) for n,c,sid,l in raw if urls.get(sid)]
    if resolved:
        M3U_FILE.parent.mkdir(exist_ok=True)
        M3U_FILE.write_text("\n".join(["#EXTM3U"] + [f'#EXTINF:-1 tvg-name="{n.replace('"',"'")}" tvg-logo="{l}" group-title="{c[0] if c else ""}",{n.replace('"',"'")}\n{u}' for n,c,_,l,u in resolved]), encoding="utf-8")
    return len(raw), len(resolved)

def resolve_url(sid):
    try:
        r = requests.get(urljoin(BASE_URL, f"player.php?stream={sid}"), headers=HEADERS, timeout=20)
        for pat in [r'<iframe[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']', r'<source[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']', r'(https?://[^\s\'"]*\.m3u8[^\s\'"]*)']:
            if (m:=re.search(pat, r.text, re.I)): return urljoin(r.url, m.group(1).strip())
        return r.url if ".m3u8" in r.url else None
    except: return None

def upload_to_github():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    h = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = requests.get(url, headers=h).json().get("sha") if requests.get(url, headers=h).ok else None
    data = {"message": f"Update {time.strftime('%Y-%m-%d %H:%M')}", "content": requests.utils.quote(M3U_FILE.read_text()), "branch": GITHUB_BRANCH}
    if sha: data["sha"] = sha
    return requests.put(url, headers=h, json=data).ok

class LocalISPTVApp(MDApp):
    def build(self):
        self.title = "Local ISP TV"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.store = JsonStore('config.json')
        self.load_config()
        Builder.load_string(KV)
        self.sm = self.root
        self.sm.add_widget(MainScreen())
        self.sm.add_widget(SettingsScreen())
        self.sm.current = "main"
        self.setup_tv()
        self.start_auto_refresh()
        return self.sm

    def setup_tv(self):
        if Window.width > 1000:
            Window.size = (1280, 720)
            self.theme_cls.font_styles["H4"] = ["Roboto", 48, False, 0]

    def load_config(self):
        global GITHUB_TOKEN, GITHUB_REPO, GITHUB_PATH, GITHUB_BRANCH, AUTO_REFRESH_HOURS, MAX_WORKERS
        GITHUB_TOKEN = self.store.get('github_token')['value'] if self.store.exists('github_token') else ""
        GITHUB_REPO = self.store.get('github_repo')['value'] if self.store.exists('github_repo') else ""
        GITHUB_PATH = self.store.get('github_path')['value'] if self.store.exists('github_path') else "channels.m3u"
        GITHUB_BRANCH = self.store.get('github_branch')['value'] if self.store.exists('github_branch') else "main"
        AUTO_REFRESH_HOURS = float(self.store.get('interval')['value']) if self.store.exists('interval') else 2.0
        MAX_WORKERS = int(self.store.get('workers')['value']) if self.store.exists('workers') else 15

    def open_settings(self):
        s = self.sm.get_screen("settings")
        s.ids.token.text = GITHUB_TOKEN
        s.ids.repo.text = GITHUB_REPO
        s.ids.path.text = GITHUB_PATH
        s.ids.branch.text = GITHUB_BRANCH
        s.ids.interval.text = str(AUTO_REFRESH_HOURS)
        s.ids.workers.text = str(MAX_WORKERS)
        self.sm.current = "settings"

    def start_auto_refresh(self):
        if hasattr(self, 'timer'): self.timer.cancel()
        self.timer = Clock.schedule_once(self.auto_upload, AUTO_REFRESH_HOURS * 3600)
        self.update_timer(AUTO_REFRESH_HOURS * 3600)

    def update_timer(self, sec):
        h, rem = divmod(int(sec), 3600)
        m, s = divmod(rem, 60)
        self.sm.get_screen("main").ids.timer.text = f"Next: {h:02d}:{m:02d}:{s:02d}"
        Clock.schedule_once(lambda dt: self.update_timer(sec - 1), 1)

    def auto_upload(self, dt):
        self.sm.get_screen("main").scrape_and_upload()
        self.start_auto_refresh()

if __name__ == '__main__':
    LocalISPTVApp().run()
