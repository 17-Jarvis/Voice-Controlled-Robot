import socket
import re
import threading
import time
import whisper
import numpy as np
import pyaudio

# Initialize Whisper model
model = whisper.load_model("base")

# Connection settings
HOST = "192.168.1.20"
PORT = 10003
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    sock.connect((HOST, PORT))
except ConnectionRefusedError:
    print("Error: Connection refused")
    exit()

# Initial joint positions
J1 = 0.400
J2 = -113.980
J3 = 162.100
J4 = 0.560
J5 = 43.930
J6 = 1.730

move_joint_flag = False
joint_lock = threading.Lock()

# Function to send a message and confirm
def send_message_and_confirm(sock, message):
    try:
        print(f"sending message: {message}")
        sock.sendall(message.encode())
        response = sock.recv(1024).decode()
        print(f"Received response: {response}")
        return response.strip() == "True"
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

# Whisper-based continuous speech recognition
def recognize_speech_whisper():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)

    print("Listening with Whisper...")
    
    audio_frames = []

    try:
        while True:
            data = stream.read(1024)
            audio_frames.append(np.frombuffer(data, np.int16).astype(np.float32) / 32768.0)

            # Convert the audio to a numpy array
            if len(audio_frames) > 100:  # Every 100 frames, process the audio
                audio_data = np.concatenate(audio_frames, axis=0)
                audio_frames = []  # Reset the buffer

                # Process with Whisper
                mel = whisper.log_mel_spectrogram(audio_data).to(model.device)
                options = whisper.DecodingOptions()
                result = model.decode(mel, options)
                text = result.text.strip().lower()
                print(f"Recognized text: {text}")

                if text:
                    return text
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

# Adjust joint movements based on command
def changes(joint_num, command, joint_value):
    adjustments = 0
    if joint_num in ['1', '4', '6']:
        if 'right' in command:
            adjustments = 5 
        elif 'left' in command:
            adjustments = -5
    elif joint_num in ['3', '5']:
        if 'up' in command:
            adjustments = 5
        elif 'down' in command:
            adjustments = -5
    elif joint_num == '2':
        if 'up' in command:
            adjustments = -5
        elif 'down' in command:
            adjustments = 5

    return joint_value + adjustments

# Continuous joint movement
def move_joint_continuously(command, joint_num):
    global J1, J2, J3, J4, J5, J6, move_joint_flag

    while move_joint_flag:
        with joint_lock:
            if joint_num == '1':
                J1 = changes('1', command, J1)
            elif joint_num == '2':
                J2 = changes('2', command, J2)
            elif joint_num == '3':
                J3 = changes('3', command, J3)
            elif joint_num == '4':
                J4 = changes('4', command, J4)
            elif joint_num == '5':
                J5 = changes('5', command, J5)
            elif joint_num == '6':
                J6 = changes('6', command, J6)
            
            message = f"1,({J1:.3f},{J2:.3f},{J3:.3f},{J4:.3f},{J5:.3f},{J6:.3f})(3,0)"
        
        send = send_message_and_confirm(sock, message)
        if send:
            print(f'Coordinates passed {message} for J{joint_num}')

        time.sleep(0.5)

# Main loop
if __name__ == '__main__':
    joints = ['1', '2', '3', '4', '5', '6']
    joint_thread = None

    while True:
        command = recognize_speech_whisper()
        if not command:
            continue
        
        if command == "exit":
            move_joint_flag = False
            if joint_thread and joint_thread.is_alive():
                joint_thread.join()
            break

        if "stop" in command:
            move_joint_flag = False
            if joint_thread and joint_thread.is_alive():
                joint_thread.join()
            print('Movement Stopped')
            continue

        joint_pattern = r'\bj(' + '|'.join(joints) + r')\b'
        match = re.search(joint_pattern, command)
        if match:
            joint_number = match.group()[1:]
        else:
            print("Joint is not recognized")
            continue

        if joint_number in joints:
            if joint_thread and joint_thread.is_alive():
                move_joint_flag = False
                joint_thread.join()

            move_joint_flag = True
            joint_thread = threading.Thread(target=move_joint_continuously, args=(command, joint_number))
            joint_thread.start()

sock.close()
