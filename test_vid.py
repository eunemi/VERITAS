import cv2
import tempfile
import urllib.request
import os

url = "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
req = urllib.request.urlopen(url)
data = req.read(2000000) # download first 2MB

fd, path = tempfile.mkstemp(suffix=".mp4")
try:
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    cap = cv2.VideoCapture(path)
    # get middle frame
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Total frames: {total_frames}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
    ret, frame = cap.read()
    if ret:
        ret, buf = cv2.imencode('.jpg', frame)
        print(f"Frame extracted, bytes: {len(buf.tobytes())}")
finally:
    if os.path.exists(path):
        os.remove(path)
