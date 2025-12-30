import board, digitalio, math, array, time
import audiobusio, displayio, busio, terminalio
import keypad, microcontroller, usb_midi, adafruit_midi
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from fourwire import FourWire
from adafruit_st7735r import ST7735R
from adafruit_display_text import label

STATE_MENU   = 0
STATE_VOLUME = 1
STATE_OUTPUT = 2
STATE_OCTAVE = 3
STATE_WAVE   = 4

OUTPUT_LINE = 0
OUTPUT_SPK  = 1
OUTPUT_MIDI = 2

WAVE_SINE   = 0
WAVE_SQUARE = 1

DEBOUNCE_TIME = 0.15

KEY_UP    = 9
KEY_DOWN  = 13
KEY_LEFT  = 23
KEY_RIGHT = 27
KEY_CLICK = 37
NAV_KEYS = (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_CLICK)

if microcontroller.nvm[0] == 0xAA:
    VOLUME = microcontroller.nvm[1] / 100
    output_mode = microcontroller.nvm[2]
    octave_offset = microcontroller.nvm[3]
    wave_type = microcontroller.nvm[4]
else:
    VOLUME = 0.4
    output_mode = OUTPUT_LINE
    octave_offset = 0
    wave_type = WAVE_SINE
    microcontroller.nvm[0] = 0xAA

amp_speaker = digitalio.DigitalInOut(board.GP13)
amp_jack    = digitalio.DigitalInOut(board.GP14)
amp_speaker.direction = amp_jack.direction = digitalio.Direction.OUTPUT

displayio.release_displays()
spi = busio.SPI(clock=board.GP16, MOSI=board.GP17)
display_bus = FourWire(spi, command=board.GP19,
                       chip_select=board.GP18, reset=board.GP20)
display = ST7735R(display_bus, width=128, height=160, rotation=270)

root = displayio.Group()
display.root_group = root

bg = displayio.Bitmap(128, 160, 1)
pal = displayio.Palette(1)
pal[0] = 0x000000
root.append(displayio.TileGrid(bg, pixel_shader=pal))

title = label.Label(terminalio.FONT, text="ORPHEUS", color=0x00FF00, x=30, y=10)
status = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=10, y=40)
root.append(title)
root.append(status)

menu_labels = []
menu_texts = ["VOL", "OUT", "OCT", "WAVE"]

keys = keypad.KeyMatrix(
    rows=(board.GP0, board.GP1, board.GP2, board.GP3, board.GP4, board.GP5),
    columns=(board.GP6, board.GP7, board.GP8, board.GP9,
             board.GP10, board.GP11, board.GP12)
)

encoder = keypad.IncrementalEncoder(board.GP21, board.GP22)

audio = audiobusio.I2SOut(
    bit_clock=board.GP26,
    word_select=board.GP27,
    data=board.GP28
)

SAMPLE_RATE = 22050
BUFFER = array.array("h", [0]*256)
phase = 0
phase_inc = 0
sine = [int(32767 * math.sin(2*math.pi*i/256)) for i in range(256)]

midi = adafruit_midi.MIDI(
    midi_out=usb_midi.ports[1],
    out_channel=0
)

current_note = None

def note_to_freq(note):
    return 440 * (2 ** ((note - 69) / 12))

def update_output():
    global phase_inc
    phase_inc = 0
    amp_jack.value    = (output_mode == OUTPUT_LINE)
    amp_speaker.value = (output_mode == OUTPUT_SPK)

def save_settings():
    microcontroller.nvm[1] = int(VOLUME * 100)
    microcontroller.nvm[2] = output_mode
    microcontroller.nvm[3] = octave_offset
    microcontroller.nvm[4] = wave_type

def draw_status(text):
    status.text = text

def draw_menu():
    global menu_labels
    for lbl in menu_labels:
        root.remove(lbl)
    menu_labels.clear()

    x_pos = [10, 70]
    y_pos = [60, 90]

    for i, text in enumerate(menu_texts):
        color = 0x00FF00 if i == menu_index else 0xFFFFFF
        lbl = label.Label(terminalio.FONT, text=text, color=color,
                          x=x_pos[i % 2], y=y_pos[i // 2])
        root.append(lbl)
        menu_labels.append(lbl)

ui_state = STATE_MENU
menu_index = 0
last_input = 0
draw_menu()

while True:
    now = time.monotonic()

    event = keys.events.get()
    if event:

        if event.pressed and event.key_number in NAV_KEYS:
            if now - last_input > DEBOUNCE_TIME:
                last_input = now

                if event.key_number == KEY_CLICK:
                    if ui_state == STATE_MENU:
                        ui_state = [STATE_VOLUME, STATE_OUTPUT,
                                    STATE_OCTAVE, STATE_WAVE][menu_index]
                    else:
                        ui_state = STATE_MENU
                        save_settings()
                        draw_menu()

                elif ui_state == STATE_MENU:
                    if event.key_number == KEY_UP:
                        menu_index = max(0, menu_index - 2)
                    elif event.key_number == KEY_DOWN:
                        menu_index = min(3, menu_index + 2)
                    elif event.key_number == KEY_LEFT:
                        menu_index = max(0, menu_index - 1)
                    elif event.key_number == KEY_RIGHT:
                        menu_index = min(3, menu_index + 1)
                    draw_menu()

        elif event.pressed:
            note = 48 + event.key_number + octave_offset * 12
            phase_inc = int(note_to_freq(note) * 256 / SAMPLE_RATE)

            if output_mode == OUTPUT_MIDI:
                midi.send(NoteOn(note, int(VOLUME * 127)))
                current_note = note

        elif event.released:
            if current_note is not None:
                midi.send(NoteOff(current_note, 0))
                current_note = None
            phase_inc = 0

    enc = encoder.events.get()
    if enc and now - last_input > DEBOUNCE_TIME:
        last_input = now

        if ui_state == STATE_VOLUME:
            VOLUME = max(0, min(0.8, VOLUME + enc.position_change * 0.05))
            draw_status(f"VOL {int(VOLUME*100)}%")

        elif ui_state == STATE_OUTPUT:
            output_mode = (output_mode + enc.position_change) % 3
            update_output()
            draw_status(["LINE","SPK","MIDI"][output_mode])

        elif ui_state == STATE_OCTAVE:
            octave_offset = max(-2, min(2, octave_offset + enc.position_change))
            draw_status(f"OCT {octave_offset}")

        elif ui_state == STATE_WAVE:
            wave_type = (wave_type + enc.position_change) % 2
            draw_status(["SINE","SQUARE"][wave_type])

    if output_mode != OUTPUT_MIDI:
        for i in range(len(BUFFER)):
            phase = (phase + phase_inc) & 0xFF
            BUFFER[i] = int(sine[phase] * VOLUME)
        audio.write(BUFFER)
