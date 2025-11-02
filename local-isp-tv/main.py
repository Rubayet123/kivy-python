from kivy.lang import Builder
from kivy.uix.screenmanager import Screen, ScreenManager
from kivymd.app import MDApp
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.dialog import MDDialog
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.utils import platform
import requests
import re
import time
import threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64

# Android imports
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
    MDBoxLayout:
        orientation: "vertical"
        padding: dp(20)
        spacing: dp(12)
        md_bg_color: app.theme_cls.bg_darkest
        
        MDTopAppBar:
            title: "Settings"
            left_action_items: [["arrow-left", lambda x: app.go_main()]]
            elevation: 2
            size_hint_y: None
            height: dp(56)
        
        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                spacing: dp(12)
                padding: dp(10)
                size_hint_y: None
                height: self.minimum_height
                
                MDLabel:
                    text: "GitHub Configuration"
                    font_style: "H6"
                    size_hint_y: None
                    height: dp(40)
                    
                MDTextField:
                    id: token
                    hint_text: "GitHub Personal Access Token"
                    helper_text: "Required for uploading to GitHub"
                    helper_text_mode: "on_focus"
                    password: True
                    icon_right: "eye-off"
                    size_hint_y: None
                    height: dp(56)
                    
                MDTextField:
                    id: repo
                    hint_text: "Repository (username/repo)"
                    helper_text: "e.g., yourusername/iptv-playlist"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                    
                MDTextField:
                    id: path
                    hint_text: "File Path in Repository"
                    text: "channels.m3u"
                    helper_text: "e.g., channels.m3u or playlists/tv.m3u"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                    
                MDTextField:
                    id: branch
                    hint_text: "Branch Name"
                    text: "main"
                    helper_text: "Usually 'main' or 'master'"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                
                MDLabel:
                    text: "Performance Settings"
                    font_style: "H6"
                    size_hint_y: None
                    height: dp(40)
                    padding_top: dp(10)
                    
                MDTextField:
                    id: interval
                    hint_text: "Auto-refresh Interval (hours)"
                    text: "2.0"
                    input_filter: "float"
                    helper_text: "Minimum: 0.5 hours"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                    
                MDTextField:
                    id: workers
                    hint_text: "Parallel Workers"
                    text: "15"
                    input_filter: "int"
                    helper_text: "5-30 workers (more = faster but uses more resources)"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                
                MDTextField:
                    id: timeout
                    hint_text: "Request Timeout (seconds)"
                    text: "15"
                    input_filter: "int"
                    helper_text: "Timeout for each request (5-30 seconds)"
                    helper_text_mode: "on_focus"
                    size_hint_y: None
                    height: dp(56)
                
                Widget:
                    size_hint_y: None
                    height: dp(20)
                
                MDRaisedButton:
                    text: "Save Settings"
                    size_hint_x: 1
                    size_hint_y: None
                    height: dp(48)
                    md_bg_color: app.theme_cls.primary_color
                    on_release: root.save()
                
                MDLabel:
                    id: msg_label
                    text: ""
                    size_hint_y: None
                    height: dp(40)
                    halign: "center"

<MainScreen>:
    name: "main"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.bg_darkest
        
        MDTopAppBar:
            title: "Local ISP TV Manager"
            right_action_items: [["cog", lambda x: app.open_settings()]]
            elevation: 2
            size_hint_y: None
            height: dp(56)
        
        MDBoxLayout:
            orientation: "vertical"
            padding: dp(20)
            spacing: dp(15)
            
            MDCard:
                orientation: "vertical"
                padding: dp(15)
                spacing: dp(10)
                size_hint_y: None
                height: dp(140)
                elevation: 4
                
                MDLabel:
                    text: "Status"
                    font_style: "Subtitle1"
                    size_hint_y: None
                    height: dp(30)
                    
                MDLabel:
                    id: status
                    text: "Ready to scrape"
                    font_style: "Body1"
                    theme_text_color: "Hint"
                    
                MDLabel:
                    id: timer
                    text: "Next refresh: --:--:--"
                    font_style: "Caption"
                    theme_text_color: "Hint"
            
            MDCard:
                orientation: "vertical"
                padding: dp(15)
                spacing: dp(12)
                size_hint_y: None
                height: dp(200)
                elevation: 4
                
                MDRaisedButton:
                    text: "Scrape & Upload Now"
                    size_hint_x: 1
                    size_hint_y: None
                    height: dp(48)
                    md_bg_color: app.theme_cls.primary_color
                    on_release: root.run()
                    
                MDRaisedButton:
                    text: "Open in VLC"
                    size_hint_x: 1
                    size_hint_y: None
                    height: dp(48)
                    md_bg_color: (0.2, 0.6, 0.9, 1)
                    on_release: root.vlc()
                    
                MDRaisedButton:
                    id: pause_btn
                    text: "Pause Auto-Refresh"
                    size_hint_x: 1
                    size_hint_y: None
                    height: dp(48)
                    md_bg_color: (0.9, 0.5, 0.2, 1)
                    on_release: root.toggle_pause()
            
            Widget:
'''

# Configuration defaults
BASE_URL = "http://redforce.live/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": BASE_URL}
M3U_FILE = Path("/storage/emulated/0/Download/channels.m3u")
REQUEST_TIMEOUT = 15

class Config:
    """Configuration manager"""
    def __init__(self):
        self.token = ""
        self.repo = ""
        self.path = "channels.m3u"
        self.branch = "main"
        self.interval = 2.0
        self.workers = 15
        self.timeout = 15
        self.paused = False

config = Config()

class SettingsScreen(Screen):
    def save(self):
        app = MDApp.get_running_app()
        
        # Validate inputs
        token = self.ids.token.text.strip()
        repo = self.ids.repo.text.strip()
        path = self.ids.path.text.strip()
        branch = self.ids.branch.text.strip()
        
        try:
            interval = float(self.ids.interval.text or 2.0)
            workers = int(self.ids.workers.text or 15)
            timeout = int(self.ids.timeout.text or 15)
        except ValueError:
            self.show_message("Invalid numeric values", error=True)
            return
        
        # Validation
        errors = []
        if token and not self.validate_token(token):
            errors.append("Invalid GitHub token or insufficient permissions")
        if repo and not re.match(r'^[\w\-\.]+/[\w\-\.]+$', repo):
            errors.append("Invalid repository format (use: username/repo)")
        if path and (path.startswith('/') or '..' in path):
            errors.append("Invalid file path")
        if not branch:
            errors.append("Branch name is required")
        if interval < 0.5:
            errors.append("Interval must be at least 0.5 hours")
        if workers < 5 or workers > 30:
            errors.append("Workers must be between 5 and 30")
        if timeout < 5 or timeout > 30:
            errors.append("Timeout must be between 5 and 30 seconds")
        
        if errors:
            self.show_message("\n".join(f"• {e}" for e in errors), error=True)
            return
        
        # Save to storage
        app.store.put('github_token', value=token)
        app.store.put('github_repo', value=repo)
        app.store.put('github_path', value=path)
        app.store.put('github_branch', value=branch)
        app.store.put('interval', value=interval)
        app.store.put('workers', value=workers)
        app.store.put('timeout', value=timeout)
        
        # Update config
        config.token = token
        config.repo = repo
        config.path = path
        config.branch = branch
        config.interval = interval
        config.workers = workers
        config.timeout = timeout
        
        self.show_message("Settings saved successfully!", error=False)
        Clock.schedule_once(lambda dt: app.go_main(), 1.5)
        app.refresh_timer()

    def validate_token(self, token):
        """Validate GitHub token"""
        try:
            r = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}"},
                timeout=10
            )
            if r.status_code == 200:
                scopes = r.headers.get("X-OAuth-Scopes", "")
                return "repo" in scopes or "public_repo" in scopes
            return False
        except Exception as e:
            print(f"Token validation error: {e}")
            return False

    def show_message(self, message, error=False):
        """Show message to user"""
        self.ids.msg_label.text = message
        self.ids.msg_label.theme_text_color = "Error" if error else "Primary"
        Clock.schedule_once(lambda dt: setattr(self.ids.msg_label, 'text', ''), 5)


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scraping = False

    def run(self):
        """Start scraping process"""
        if self.scraping:
            self.show_dialog("Already Running", "Please wait for the current operation to complete.")
            return
        
        if platform == 'android' and not self.is_online():
            self.show_dialog("No Internet", "Please check your internet connection.")
            return
        
        self.ids.status.text = "Initializing scraper..."
        self.scraping = True
        self.acquire_wake_lock()
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        """Background worker for scraping and uploading"""
        try:
            # Scraping phase
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', "Scraping channels..."))
            total, successful = scrape_channels()
            
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', 
                f"Found {total} channels, resolved {successful} streams. Uploading..."))
            
            # Upload phase
            if config.token and config.repo:
                upload_success = upload_to_github()
                status = "✓ Success" if upload_success else "✗ Upload failed"
            else:
                status = "✓ Saved locally (GitHub not configured)"
            
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', 
                f"{status}: {successful}/{total} channels"))
            
        except Exception as e:
            error_msg = f"Error: {str(e)[:50]}"
            Clock.schedule_once(lambda dt: setattr(self.ids.status, 'text', error_msg))
            print(f"Worker error: {e}")
        finally:
            self.scraping = False
            self.release_wake_lock()

    def vlc(self):
        """Open M3U file in VLC"""
        if not M3U_FILE.exists():
            self.show_dialog("No Playlist", "Please scrape channels first.")
            return
        
        if platform == 'android':
            try:
                from jnius import autoclass
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                File = autoclass('java.io.File')
                
                intent = Intent(Intent.ACTION_VIEW)
                file_uri = Uri.fromFile(File(str(M3U_FILE)))
                intent.setDataAndType(file_uri, "audio/x-mpegurl")
                intent.setPackage("org.videolan.vlc")
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                
                activity.startActivity(intent)
            except Exception as e:
                self.show_dialog("Error", f"Could not open VLC: {str(e)[:50]}")
        else:
            self.show_dialog("Desktop Mode", f"Playlist saved at: {M3U_FILE}")

    def toggle_pause(self):
        """Toggle auto-refresh pause state"""
        app = MDApp.get_running_app()
        config.paused = not config.paused
        app.store.put('paused', value=config.paused)
        
        if config.paused:
            self.ids.pause_btn.text = "Resume Auto-Refresh"
            self.ids.pause_btn.md_bg_color = (0.8, 0.3, 0.3, 1)
            self.ids.timer.text = "Auto-refresh paused"
        else:
            self.ids.pause_btn.text = "Pause Auto-Refresh"
            self.ids.pause_btn.md_bg_color = (0.9, 0.5, 0.2, 1)
            app.refresh_timer()

    def is_online(self):
        """Check internet connectivity (Android)"""
        if platform != 'android':
            return True
        try:
            cm = activity.getSystemService(ConnectivityManager)
            network = cm.getActiveNetworkInfo()
            return network and network.isConnected()
        except:
            return True

    def acquire_wake_lock(self):
        """Acquire wake lock to prevent sleep during scraping"""
        if platform == 'android' and not hasattr(self, 'wake_lock'):
            try:
                pm = activity.getSystemService(PowerManager)
                self.wake_lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ISP:Scraper")
                self.wake_lock.acquire()
            except Exception as e:
                print(f"Wake lock error: {e}")

    def release_wake_lock(self):
        """Release wake lock"""
        if platform == 'android' and hasattr(self, 'wake_lock'):
            try:
                if self.wake_lock.isHeld():
                    self.wake_lock.release()
            except Exception as e:
                print(f"Wake lock release error: {e}")

    def show_dialog(self, title, text=""):
        """Show dialog to user"""
        MDDialog(
            title=title,
            text=text,
            size_hint=(0.8, None),
            height=dp(200)
        ).open()


def scrape_channels():
    """Scrape channels from website"""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # Fetch main page
        response = session.get(BASE_URL, timeout=config.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract channel information
        channels = []
        for li in soup.select("ul#vidlink li"):
            try:
                anchor = li.find("a", {"onclick": True})
                if not anchor:
                    continue
                
                img = anchor.find("img")
                if not img:
                    continue
                
                name = img.get("alt", "").strip()
                logo = urljoin(BASE_URL, img.get("src", ""))
                
                # Extract stream ID
                onclick = anchor.get("onclick", "")
                match = re.search(r"stream=(\d+)", onclick)
                if not match:
                    continue
                stream_id = match.group(1)
                
                # Extract categories
                categories = [c for c in li.get("class", []) if c != "All"]
                category = categories[0] if categories else "Uncategorized"
                
                channels.append({
                    "name": name,
                    "id": stream_id,
                    "logo": logo,
                    "category": category
                })
            except Exception as e:
                print(f"Error parsing channel: {e}")
                continue
        
        if not channels:
            print("No channels found")
            return 0, 0
        
        # Resolve stream URLs concurrently
        resolved_channels = []
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            future_to_channel = {
                executor.submit(resolve_stream_url, ch["id"]): ch 
                for ch in channels
            }
            
            for future in as_completed(future_to_channel):
                channel = future_to_channel[future]
                try:
                    stream_url = future.result()
                    if stream_url:
                        channel["url"] = stream_url
                        resolved_channels.append(channel)
                except Exception as e:
                    print(f"Error resolving {channel['name']}: {e}")
        
        # Generate M3U playlist
        if resolved_channels:
            generate_m3u_playlist(resolved_channels)
        
        return len(channels), len(resolved_channels)
    
    except Exception as e:
        print(f"Scraping error: {e}")
        raise


def resolve_stream_url(stream_id):
    """Resolve stream URL from player page"""
    try:
        url = urljoin(BASE_URL, f"player.php?stream={stream_id}")
        response = requests.get(url, headers=HEADERS, timeout=config.timeout)
        response.raise_for_status()
        
        # Patterns to find m3u8 URL
        patterns = [
            r'<iframe[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'<source[^>]+src=["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'file:\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source:\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'(https?://[^\s\'"<>]*\.m3u8[^\s\'"<>]*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response.text, re.IGNORECASE)
            if match:
                m3u8_url = match.group(1).strip()
                return urljoin(response.url, m3u8_url)
        
        # Check if redirected to m3u8
        if ".m3u8" in response.url:
            return response.url
        
        return None
    except Exception as e:
        print(f"Error resolving stream {stream_id}: {e}")
        return None


def generate_m3u_playlist(channels):
    """Generate M3U playlist file"""
    try:
        M3U_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        lines = ["#EXTM3U"]
        for ch in channels:
            name = ch["name"].replace('"', "'")
            logo = ch["logo"]
            category = ch["category"]
            url = ch["url"]
            
            lines.append(
                f'#EXTINF:-1 tvg-name="{name}" tvg-logo="{logo}" group-title="{category}",{name}'
            )
            lines.append(url)
        
        M3U_FILE.write_text("\n".join(lines), encoding="utf-8")
        print(f"Playlist saved: {M3U_FILE}")
    except Exception as e:
        print(f"Error generating playlist: {e}")
        raise


def upload_to_github():
    """Upload M3U file to GitHub"""
    try:
        if not config.token or not config.repo:
            print("GitHub not configured")
            return False
        
        url = f"https://api.github.com/repos/{config.repo}/contents/{config.path}"
        headers = {
            "Authorization": f"token {config.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Get existing file SHA (if exists)
        sha = None
        try:
            response = requests.get(url, headers=headers, params={"ref": config.branch}, timeout=10)
            if response.status_code == 200:
                sha = response.json().get("sha")
        except:
            pass
        
        # Read and encode content
        content = M3U_FILE.read_bytes()
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        # Prepare commit data
        data = {
            "message": f"Update playlist {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "content": encoded_content,
            "branch": config.branch
        }
        
        if sha:
            data["sha"] = sha
        
        # Upload
        response = requests.put(url, headers=headers, json=data, timeout=15)
        
        if response.status_code in [200, 201]:
            print("Successfully uploaded to GitHub")
            return True
        else:
            print(f"GitHub upload failed: {response.status_code} - {response.text}")
            return False
    
    except Exception as e:
        print(f"GitHub upload error: {e}")
        return False


class LocalISPTVApp(MDApp):
    def build(self):
        self.title = "Local ISP TV Manager"
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        
        # Load configuration
        self.store = JsonStore('config.json')
        self.load_config()
        
        # Build UI
        Builder.load_string(KV)
        self.sm = ScreenManager()
        self.sm.add_widget(MainScreen())
        self.sm.add_widget(SettingsScreen())
        
        # Set initial screen
        self.sm.current = "main"
        
        # Set window size for desktop
        if Window.width > 1000:
            Window.size = (400, 700)
        
        # Start auto-refresh timer
        self.refresh_timer()
        
        return self.sm

    def load_config(self):
        """Load configuration from storage"""
        config.token = self.store.get('github_token').get('value', '') if self.store.exists('github_token') else ''
        config.repo = self.store.get('github_repo').get('value', '') if self.store.exists('github_repo') else ''
        config.path = self.store.get('github_path').get('value', 'channels.m3u') if self.store.exists('github_path') else 'channels.m3u'
        config.branch = self.store.get('github_branch').get('value', 'main') if self.store.exists('github_branch') else 'main'
        config.interval = self.store.get('interval').get('value', 2.0) if self.store.exists('interval') else 2.0
        config.workers = self.store.get('workers').get('value', 15) if self.store.exists('workers') else 15
        config.timeout = self.store.get('timeout').get('value', 15) if self.store.exists('timeout') else 15
        config.paused = self.store.get('paused').get('value', False) if self.store.exists('paused') else False

    def open_settings(self):
        """Open settings screen"""
        screen = self.sm.get_screen("settings")
        screen.ids.token.text = config.token
        screen.ids.repo.text = config.repo
        screen.ids.path.text = config.path
        screen.ids.branch.text = config.branch
        screen.ids.interval.text = str(config.interval)
        screen.ids.workers.text = str(config.workers)
        screen.ids.timeout.text = str(config.timeout)
        self.sm.current = "settings"

    def go_main(self):
        """Return to main screen"""
        self.sm.current = "main"

    def refresh_timer(self):
        """Setup auto-refresh timer"""
        if hasattr(self, 'timer_event'):
            self.timer_event.cancel()
        
        if config.paused:
            return
        
        interval_seconds = config.interval * 3600
        self.timer_event = Clock.schedule_once(self.auto_refresh, interval_seconds)
        self.update_countdown(interval_seconds)

    def update_countdown(self, remaining):
        """Update countdown timer display"""
        if config.paused:
            return
        
        if remaining <= 0:
            return
        
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        seconds = int(remaining % 60)
        
        main_screen = self.sm.get_screen("main")
        main_screen.ids.timer.text = f"Next refresh: {hours:02d}:{minutes:02d}:{seconds:02d}"
        
        Clock.schedule_once(lambda dt: self.update_countdown(remaining - 1), 1)

    def auto_refresh(self, dt):
        """Perform automatic refresh"""
        if not config.paused:
            main_screen = self.sm.get_screen("main")
            main_screen.run()
        self.refresh_timer()


if __name__ == '__main__':
    LocalISPTVApp().run()
