import board
import digitalio
import math
import array
import audiobusio
import displayio
import busio
import terminalio
from fourwire import FourWire
from adafruit_st7735r import ST7735R
from adafruit_display_text import label
import keypad

# -----------------------------------------------------
# AMPLIFICADORES (SHDN)
# -----------------------------------------------------

amp_speaker = digitalio.DigitalInOut(board.GP13)
amp_speaker.direction = digitalio.Direction.OUTPUT

amp_jack = digitalio.DigitalInOut(board.GP14)
amp_jack.direction = digitalio.Direction.OUTPUT

# Speaker activo por defecto
amp_speaker.value = True
amp_jack.value = False

# -----------------------------------------------------
# LCD BACKLIGHT
# -----------------------------------------------------

lcd_bl = digitalio.DigitalInOut(board.GP15)
lcd_bl.direction = digitalio.Direction.OUTPUT
lcd_bl.value = True

# -----------------------------------------------------
# DISPLAY ST7735R
# -----------------------------------------------------

displayio.release_displays()

spi = busio.SPI(clock=board.GP16, MOSI=board.GP17)
display_bus = FourWire(
    spi,
    command=board.GP19,
    chip_select=board.GP18,
    reset=board.GP20
)

display = ST7735R(
    display_bus,
    width=128,
    height=160,
    rotation=270
)

# -----------------------------------------------------
# UI BASE
# -----------------------------------------------------

splash = displayio.Group()
display.root_group = splash

bg_bitmap = displayio.Bitmap(128, 160, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x000000

splash.append(displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette))

title = label.Label(
    terminalio.FONT,
    text="ORPHEUS SYNTH",
    color=0x00FF00,
    x=10,
    y=10
)
splash.append(title)

volume_label = label.Label(
    terminalio.FONT,
    text="VOL: 40%",
    color=0xFFFFFF,
    x=10,
    y=30
)
splash.append(volume_label)

# -----------------------------------------------------
# MATRIZ DE TECLAS
# -----------------------------------------------------

keys = keypad.KeyMatrix(
    rows=(board.GP0, board.GP1, board.GP2, board.GP3, board.GP4, board.GP5),
    columns=(board.GP6, board.GP7, board.GP8, board.GP9, board.GP10, board.GP11, board.GP12)
)

# -----------------------------------------------------
# ROTARY ENCODER (VOLUMEN)
# -----------------------------------------------------

encoder = keypad.IncrementalEncoder(board.GP21, board.GP22)

# -----------------------------------------------------
# AUDIO I2S (PCM5100)
# -----------------------------------------------------

audio = audiobusio.I2SOut(
    bit_clock=board.GP26,
    word_select=board.GP27,
    data=board.GP28
)

SAMPLE_RATE = 22050
BUFFER_SIZE = 256

VOLUME = 0.4
VOLUME_MIN = 0.0
VOLUME_MAX = 0.8
VOLUME_STEP = 0.05

sine = [
    int(32767 * math.sin(2 * math.pi * i / 256))
    for i in range(256)
]

phase = 0
phase_inc = 0
buffer = array.array("h", [0] * BUFFER_SIZE)

BASE_NOTE = 48  # C3

def note_to_freq(note):
    return 440 * (2 ** ((note - 69) / 12))

# -----------------------------------------------------
# BUCLE PRINCIPAL
# -----------------------------------------------------

while True:

    # --- Teclas ---
    event = keys.events.get()
    if event and event.pressed:
        note = BASE_NOTE + event.key_number
        freq = note_to_freq(note)
        phase_inc = int(freq * 256 / SAMPLE_RATE)

    # --- Encoder (Volumen) ---
    enc_event = encoder.events.get()
    if enc_event and enc_event.position_change != 0:
        VOLUME += enc_event.position_change * VOLUME_STEP
        VOLUME = max(VOLUME_MIN, min(VOLUME, VOLUME_MAX))
        volume_label.text = "VOL: {}%".format(int(VOLUME * 100))

    # --- Audio ---
    for i in range(BUFFER_SIZE):
        phase = (phase + phase_inc) & 0xFF
        buffer[i] = int(sine[phase] * VOLUME)

    audio.write(buffer)