import os
import socket
import threading
import whisper
import time
import re
import pyaudio
import wave
from bluetooth import *

HOST = "192.168.1.20"
PORT = 10003
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    sock.connect((HOST, PORT))
except ConnectionRefusedError:
    print("Error: Connection Refused")
    exit()

J1, J2, J3, J4, J5, J6 = 0.400, -113.980, 162.100, 0.560, 43.930, 1.730
move_joint_flag = False
message_sent = False  # Tracks if the first message was sent
initial_tap = True  # Flag to detect initial mic activation

joint_lock = threading.Lock()
condition = threading.Condition()

def send_message_and_confirm(sock, message):
    global message_sent
    try:
        print(f"Sending message: {message}")
        sock.sendall(message.encode())
        response = sock.recv(1024).decode()
        print(f"Received Message: {response}")
        if response.strip() == "True":
            message_sent = True
        return response.strip() == "True"
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def recognize_speech(audio_file_path):
    model = whisper.load_model("tiny")
    audio = whisper.load_audio(audio_file_path)
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio).to(model.device)
    _, probs = model.detect_language(mel)
    print(f"Detected language: {max(probs, key=probs.get)}")
    options = whisper.DecodingOptions()
    result = whisper.decode(model, mel, options)
    os.remove(audio_file_path)  # Remove the file after processing
    return result.text

def record_audio(duration=5, file_name="audio.mp3"):
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=44100, input=True, frames_per_buffer=1024)
    frames = []
    print("Recording...")

    for _ in range(0, int(44100 / 1024 * duration)):
        data = stream.read(1024)
        frames.append(data)

    print("Recording finished.")
    stream.stop_stream()
    stream.close()
    p.terminate()

    wf = wave.open(file_name, 'wb')
    wf.setnchannels(1)
    wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
    wf.setframerate(44100)
    wf.writeframes(b''.join(frames))
    wf.close()

def bluetooth_mic_tapped(device_name="Bluetooth Mic"):
    # Detect if the Bluetooth mic is connected/tapped. Adjust this logic based on device-specific behavior.
    nearby_devices = discover_devices(lookup_names=True)
    for addr, name in nearby_devices:
        if device_name in name:
            print(f"{device_name} is tapped (connected)")
            return True
    return False

def changes(joint_num, co_direction, joint_value):
    adjustments = 0
    if 'plus' in co_direction.lower() or '+' in co_direction:
        adjustments = 5
    elif 'minus' in co_direction.lower() or '-' in co_direction or 'left' in co_direction.lower():
        adjustments = -5
    return joint_value + adjustments

def move_joint_continuously(joint_num, com_direction):
    global J1, J2, J3, J4, J5, J6, move_joint_flag
    while move_joint_flag:
        with joint_lock:
            if joint_num == '1':
                J1 = changes('1', com_direction, J1)
            elif joint_num == '2':
                J2 = changes('2', com_direction, J2)
            elif joint_num == '3':
                J3 = changes('3', com_direction, J3)
            elif joint_num == '4':
                J4 = changes('4', com_direction, J4)
            elif joint_num == '5':
                J5 = changes('5', com_direction, J5)
            elif joint_num == '6':
                J6 = changes('6', com_direction, J6)
            message = f"1,({J1:.3f},{J2:.3f},{J3:.3f},{J4:.3f},{J5:.3f},{J6:.3f})(3,0)"
            send = send_message_and_confirm(sock, message)
            if send:
                print(f"Coordinates passed: {message} for J{joint_num}")
        with condition:
            condition.wait(timeout=0.1)

try:
    joint_thread = None
    while True:
        if bluetooth_mic_tapped():
            if initial_tap:
                # Handle the initial tap without checking message_sent
                print("Initial tap detected, recording first command...")
                record_audio(5, "audio.mp3")
                command = recognize_speech("audio.mp3")
                initial_tap = False  # Set initial_tap to False after the first command
            elif message_sent:
                # For subsequent taps, stop movement and process new command
                move_joint_flag = False
                if joint_thread and joint_thread.is_alive():
                    with condition:
                        condition.notify_all()
                    joint_thread.join()
                print("Bluetooth mic tapped, stopping movement and recording new command...")
                record_audio(5, "audio.mp3")
                command = recognize_speech("audio.mp3")

                # Stop if "stop" command is received
                if "stop" in command.lower():
                    print('Movement stopped due to "stop" command')
                    continue

                # Match and execute a valid movement command
                match = re.match(r'j(\d+)\s+move\s+(\w+)', command.lower())
                if match:
                    joint_num, com_direction = match.groups()
                    if joint_num in ['1', '2', '3', '4', '5', '6']:
                        move_joint_flag = True
                        if joint_thread and joint_thread.is_alive():
                            with condition:
                                condition.notify_all()
                            joint_thread.join()
                        joint_thread = threading.Thread(target=move_joint_continuously, args=(joint_num, com_direction))
                        joint_thread.start()
                    else:
                        print("Invalid joint number specified.")
                else:
                    print("Invalid command format.")
finally:
    sock.close()
    print("Socket closed")
