"""Runtime configuration. Everything here can be overridden by CLI flags
(see run_pc.py) or from the Settings panel in the UI."""

# Where the PC app serves its own UI (desktop + mobile both use this).
HOST = "0.0.0.0"
PORT = 8420

# Robot connection: the 4-character serial printed on the robot, or its
# IP / hostname. None = let the SDK auto-discover a single robot.
DEFAULT_ROBOT = None

# Motion tuning
DRIVE_SPEED = 0.6          # -1.0 .. 1.0
TURN_SPEED = 0.5
MOVE_DURATION = 0.4        # s per movement pulse; held keys re-send faster

# Camera
CAMERA_FPS = 6
CAMERA_JPEG_QUALITY = 60

# Auto mode
AUTO_OBSTACLE_CM = 20      # back off if sonar sees something closer
AUTO_TICK = 1.2            # s between autonomous decisions
WAKE_WORDS = ("vulkan", "hey vulkan", "hello vulkan")
