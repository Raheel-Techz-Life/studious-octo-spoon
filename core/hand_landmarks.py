"""Named indices into the 21-point MediaPipe hand landmark list.

RecognitionResult.landmarks is a flat list of (x, y) normalized coordinates
in this fixed order (MediaPipe's standard hand landmark topology).
"""

WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12
RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20


def hand_scale(landmarks: list[tuple[float, float]]) -> float:
    """Distance from wrist to middle-finger MCP, used to normalize pinch
    thresholds against hand size/distance from the camera instead of a
    fixed pixel/normalized-coordinate constant.
    """
    wx, wy = landmarks[WRIST]
    mx, my = landmarks[MIDDLE_MCP]
    return ((wx - mx) ** 2 + (wy - my) ** 2) ** 0.5


def distance(landmarks: list[tuple[float, float]], a: int, b: int) -> float:
    ax, ay = landmarks[a]
    bx, by = landmarks[b]
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def finger_extended(landmarks: list[tuple[float, float]], tip: int, pip: int, mcp: int) -> bool:
    """True if a finger is extended, judged by the tip being farther from
    the MCP than the PIP joint is (works regardless of hand rotation,
    unlike a simple y-coordinate comparison).
    """
    return distance(landmarks, mcp, tip) > distance(landmarks, mcp, pip) * 1.15
