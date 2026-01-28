@echo off
REM Assemble Epic Discovery Teaser from captured frames
REM Uses ffmpeg to stitch frames and add text overlays

set CAPTURES=output\captures
set OUTPUT=output\teaser
set FPS=30

echo ============================================
echo Assembling Epic Discovery Teaser
echo ============================================

REM Create output directory
if not exist "%OUTPUT%" mkdir "%OUTPUT%"

echo.
echo Step 1: Converting frame sequences to video clips...

REM Convert each shot to video clip
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\01_globe_reveal\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_01.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\02_giza\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_02.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\03_machu_picchu\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_03.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\04_stonehenge\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_04.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\05_filter_demo\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_05.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\06_search_demo\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_06.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\07_popup_demo\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_07.mp4"
ffmpeg -y -framerate %FPS% -i "%CAPTURES%\08_globe_outro\frame_%%05d.jpg" -c:v libx264 -pix_fmt yuv420p "%OUTPUT%\clip_08.mp4"

echo.
echo Step 2: Creating concat list...

REM Create concat file
(
echo file 'clip_01.mp4'
echo file 'clip_02.mp4'
echo file 'clip_03.mp4'
echo file 'clip_04.mp4'
echo file 'clip_05.mp4'
echo file 'clip_06.mp4'
echo file 'clip_07.mp4'
echo file 'clip_08.mp4'
) > "%OUTPUT%\concat.txt"

echo.
echo Step 3: Concatenating clips...

ffmpeg -y -f concat -safe 0 -i "%OUTPUT%\concat.txt" -c copy "%OUTPUT%\teaser_raw.mp4"

echo.
echo Step 4: Adding text overlays...

REM Add text overlays using drawtext filter
ffmpeg -y -i "%OUTPUT%\teaser_raw.mp4" ^
  -vf "drawtext=text='ANCIENT NERDS':fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,0,3)', ^
       drawtext=text='Modern Tech for Ancient Mysteries':fontsize=36:fontcolor=cyan:x=(w-text_w)/2:y=(h/2)+50:enable='between(t,1,5)', ^
       drawtext=text='800,000+ Sites':fontsize=64:fontcolor=gold:x=(w-text_w)/2:y=h-120:enable='between(t,3,9)', ^
       drawtext=text='Pyramids of Giza':fontsize=48:fontcolor=white:x=80:y=h-150:enable='between(t,9,13)', ^
       drawtext=text='Egypt':fontsize=28:fontcolor=white@0.8:x=80:y=h-100:enable='between(t,9,13)', ^
       drawtext=text='FEATURED SITE':fontsize=18:fontcolor=red:x=80:y=h-220:enable='between(t,13,17)', ^
       drawtext=text='Machu Picchu':fontsize=48:fontcolor=white:x=80:y=h-150:enable='between(t,13,17)', ^
       drawtext=text='Peru':fontsize=28:fontcolor=white@0.8:x=80:y=h-100:enable='between(t,13,17)', ^
       drawtext=text='Stonehenge':fontsize=48:fontcolor=white:x=80:y=h-150:enable='between(t,17,21)', ^
       drawtext=text='England':fontsize=28:fontcolor=white@0.8:x=80:y=h-100:enable='between(t,17,21)', ^
       drawtext=text='Filter by Type':fontsize=56:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,21,27)', ^
       drawtext=text='Search Any Site':fontsize=56:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,27,33)', ^
       drawtext=text='Rich Details':fontsize=56:fontcolor=white:x=(w-text_w)/2:y=h-100:enable='between(t,33,39)', ^
       drawtext=text='ancientnerds.com':fontsize=64:fontcolor=cyan:x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,35,42)'" ^
  -c:v libx264 -preset fast -crf 18 "%OUTPUT%\epic_discovery_teaser.mp4"

echo.
echo ============================================
echo DONE!
echo ============================================
echo.
echo Output: %OUTPUT%\epic_discovery_teaser.mp4
echo.
pause
