import socket
import re
import speech_recognition as sr
import threading
import time

recognizer = sr.Recognizer()
HOST = "192.168.1.20"
PORT = 10003
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    sock.connect((HOST, PORT))
except ConnectionRefusedError:
    print("Error: Connection refused")
    exit()

J1 = 0.400
J2 = -113.980
J3 = 162.100
J4 = 0.560
J5 = 43.930
J6 = 1.730

move_joint_flag = False

joint_lock = threading.Lock()

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

def recognize_speech():
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        recognizer.dynamic_energy_threshold = True
        
        audio_data = recognizer.listen(source, timeout=None, phrase_time_limit=None)
        
        try:
            text = recognizer.recognize_google(audio_data)
            print(f"You said: {text}")
            return text
        except sr.UnknownValueError:
            print("Sorry, I could not understand the audio")
            return ""
        except sr.RequestError:
            print("Could not request results from the speech recognition service")
            return ""

def changes(joint_num, command, joint_value):
    if joint_num in ['1', '4', '6']:
        if 'right' in command.lower():
            adjustments = 5 
        elif 'left' in command.lower():
            adjustments = -5
    elif joint_num in ['3', '5']:
        if 'up' in command.lower():
            adjustments = 5
        elif 'down' in command.lower():
            adjustments = -5
    elif joint_num == '2':
        if 'up' in command.lower():
            adjustments = -5
        elif 'down' in command.lower():
            adjustments = 5
    else:
        adjustments = 0 

    return joint_value + adjustments

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

if __name__ == '__main__':
    joints = ['1', '2', '3', '4', '5', '6']
    joint_thread = None

    while True:
        command = recognize_speech()
        if not command:
            continue
        
        if command.lower() == "exit":
            move_joint_flag = False
            if joint_thread and joint_thread.is_alive():
                joint_thread.join()
            break 

        if "stop" in command.lower():
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
