[app]
title = Local ISP TV
package.name = localisptv
package.domain = org.localisp

source.dir = .
source.include_exts = py,png,jpg,kv,xml

version = 1.0
requirements = python3,kivy==2.3.0,kivymd==2.0.0,requests,beautifulsoup4,lxml,tqdm,pyjnius,certifi

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,WAKE_LOCK
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = armeabi-v7a
android.presplash = presplash.png
android.icon = icon.png
android.tv_banner = tv_banner.png
android.manifest_intent_filters = intent-filters.xml

[buildozer]
log_level = 2
