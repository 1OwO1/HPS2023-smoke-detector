import paho.mqtt.client as mqtt  
import json
import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import smbus2
import RPi.GPIO as GPIO
import neopixel
import uuid 

# mqtt configuration
MQTT_SERVER = "rpi3"  
MQTT_PORT = 1883  
MQTT_ALIVE = 60  
MQTT_TOPIC = "/rpi/led_config"
MQTT_DEVICE_NAME = "/rpi/"

# LED stripe configuration
pixel_pin = board.D10
num_pixels = 6
ORDER = neopixel.GRB

# initialize
pixels = neopixel.NeoPixel(
    pixel_pin, num_pixels, brightness=0.1, auto_write=False, pixel_order=ORDER
)

file_name = "uuid.txt"
try:
    # Try to open the file for reading
    with open(file_name, "r") as file:
        content = file.read()
        print(f"Read UUID:\n{content}")
        device_id = uuid.UUID(content)
except FileNotFoundError:
    # If the file doesn't exist, create it and write something
    with open(file_name, "w") as file:
        device_id = uuid.uuid1()
        print(device_id)
        file.write(str(device_id))
    print(f"File '{file_name}' didn't exist and has been created.")

def led_control(num):
    for i in range(num_pixels):
        if (i <= int(num * num_pixels) + 1 and i >= int(num_pixels * num_pixels) - 1):
            pixels[i] = (0, 255, 0)
        else: 
            pixels[i] = (0, 0, 0)
    pixels.show()


def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    print(f"{msg.topic}: {msg.payload.decode('utf-8')}")
    if (msg.topic == "/rpi/led_config"):
        data = json.loads(msg.payload)
        if (data['device_id'] == device_id):
            led_control(float(data['degree']))
    else: 
        print(msg.topic)
    #print(f"{msg.topic} - data1: {json.loads(msg.payload)['data1']}, data2: {json.loads(msg.payload)['data2']}")


def Cal_temperature(bus):
    # Read LM75 Raw Datams
    LM75_Rawdata    = bus.read_word_data(LM75_address, 0)
    raw_temperature = ((LM75_Rawdata << 8) & 0xFF00) + (LM75_Rawdata >> 8) # Check Datasheet and Sample Code

    # Convert Raw to Celsius Temperature
    # Least Significant Bit is 0.5 
    Cel_temperature = (raw_temperature /128.0) * 0.5
    return Cel_temperature

def Cal_CO_ppm(ADS_out):
    Sensor_Voltage = ADS_out.voltage  
    # Sensor_Voltage = (ADS_out.value * 5) / 1023.0
    Sensor_R       = ((5 - Sensor_Voltage) / Sensor_Voltage)*10000  
    R              = (Sensor_R / 15620)
    Co_ppm        = (R**(-1.409)) * 106.13
    return Co_ppm

def Send_alarm(channel):
    payload = {
            'device_id' : str(device_id),
            'somke_detected' : True
    }
    mqtt_client.publish("/rpi/smoke_sensor", json.dumps(payload), qos=1)
    mqtt_client.loop(2,10)
    print("send_alarm")

print("Init Sensor...")
# check U Sensor I2c address
MQ7_address  = 0x4a    
LM75_address = 0x48

# Build SMBus Class for I2c
bus = smbus2.SMBus(1)
# Build ADS1115 Class
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c, address=MQ7_address)

# mqtt setup
mqtt_client = mqtt.Client()  
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_SERVER, MQTT_PORT, MQTT_ALIVE)    
#mqtt_client.loop_forever()


GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.add_event_detect(26, GPIO.FALLING,
callback=Send_alarm, bouncetime=100)

no = 1
while True: 
    # Chose ADS1115 A0 pin for Output
    ADS_out = AnalogIn(ads, ADS.P0)
    Co_ppm = Cal_CO_ppm(ADS_out)
    Cel_temperature = Cal_temperature(bus)

    # Output CO ppm
    print("CO ppm is {:}".format(Co_ppm))   
    # Output Celsius Temperature
    print("Celsius Temperature: {:} °C".format(Cel_temperature))
    payload = { 
    'ppm': Co_ppm,
    'temp': Cel_temperature 
    }
    print(f"payload: {payload}")
    mqtt_client.publish("rpi/condition", json.dumps(payload), qos=1)
    mqtt_client.loop(2,10)
    no = no + 1
    time.sleep(1)

# Close bus use I2C
bus.close()


