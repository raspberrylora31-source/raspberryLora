import cv2
import sys

print("📷 Camera Test Script")
print("=" * 50)

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Camera not detected!")
    sys.exit(1)

print("✅ Camera detected!")
print()

# Get camera properties
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = int(cap.get(cv2.CAP_PROP_FPS))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"📊 Camera Properties:")
print(f"   Resolution: {frame_width}x{frame_height}")
print(f"   FPS: {fps}")
print(f"   Total Frames: {total_frames}")
print()

# Capture a few test frames
print("📹 Capturing test frames...")
frame_count = 0
try:
    for i in range(10):
        ret, frame = cap.read()
        if not ret:
            print(f"❌ Failed to read frame {i}")
            break
        
        frame_count += 1
        if frame is None:
            print(f"❌ Frame {i} is None")
            break
        
        print(f"   Frame {i}: {frame.shape} (dtype: {frame.dtype})")

except Exception as e:
    print(f"❌ Error: {e}")

print()
print(f"✅ Successfully captured {frame_count} frames")

cap.release()
print("✅ Camera test complete!")
print("=" * 50)