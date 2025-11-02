[app]
title = Local ISP TV
package.name = localiptv
package.domain = org.localiptv
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,requests,beautifulsoup4,lxml,pyjnius
presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png
orientation = landscape
fullscreen = 0
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,WAKE_LOCK,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.private_storage = False
android.skip_update = False
android.accept_sdk_license = True
android.enable_androidx = True
android.manifest.intent_filters = intent-filters.xml
android.extra_manifest_xml = extra_manifest.xml
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.release_artifact = apk
android.debug_artifact = apk
[buildozer]
log_level = 2
warn_on_root = 0
