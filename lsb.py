#!/usr/bin/env python3
import sys
import struct
import numpy
import matplotlib.pyplot as plt

from PIL import Image
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64


def encrypt_input(data_input, password):
    # Generate a random salt
    salt = get_random_bytes(16)
    
    # Derive a key from the password
    key = PBKDF2(password, salt, dkLen=32, count=1000000)
    
    # Generate a random nonce
    nonce = get_random_bytes(12)
    
    # Create cipher object
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    
    # Encrypt the message
    ciphertext, tag = cipher.encrypt_and_digest(data_input)
    
    # Concatenate salt + nonce + ciphertext + tag
    encrypted_data = salt + nonce + ciphertext + tag
    
    # Encode the encrypted data to base64
    encrypted_base64 = base64.b64encode(encrypted_data)
    
    return encrypted_base64

def decrypt_input(encrypted_input, password):
    # Decode base64
    encrypted_data = base64.b64decode(encrypted_input)
    
    # Extract salt, nonce, ciphertext, tag
    salt = encrypted_data[:16]
    nonce = encrypted_data[16:28]
    ciphertext = encrypted_data[28:-16]
    tag = encrypted_data[-16:]
    
    # Derive key from password and salt
    key = PBKDF2(password, salt, dkLen=32, count=1000000)
    
    # Create cipher object
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    
    # Decrypt the message
    decrypted_input = cipher.decrypt_and_verify(ciphertext, tag)
    
    return decrypted_input

# Decompose a binary file into an array of bits
def decompose(data):
	v = []
	
	# Pack file len in 4 bytes
	fSize = len(data)
	packed_data = struct.pack("i", fSize)
	bytes = [b for b in packed_data]
	bytes += [ord(chr(b)) for b in data]
	
	for b in bytes:
		for i in range(7, -1, -1):
			v.append((b >> i) & 0x1)

	return v

# Assemble an array of bits into a binary file
def assemble(v):    
	bytes_data = b""

	length = len(v)
	for idx in range(0, len(v)//8):
		byte = 0
		for i in range(0, 8):
			if (idx*8+i < length):
				byte = (byte<<1) + v[idx*8+i]                
		bytes_data += bytes([byte])  #bytes = bytes + chr(byte)

	payload_size = struct.unpack("i", bytes_data[:4])[0]


	return bytes_data[4: payload_size + 4]

# Set the i-th bit of v to x
def set_bit(n, i, x):
	mask = 1 << i
	n &= ~mask
	if x:
		n |= mask
	return n

# Embed payload file into LSB bits of an image
def embed(imgFile, payload, password):
	# Process source image
	img = Image.open(imgFile)
	(width, height) = img.size
	conv = img.convert("RGBA").getdata()
	print("[*] Input image size: %dx%d pixels." % (width, height))
	max_size = width*height*3.0/8/1024		# max payload size
	print("[*] Usable payload size: %.2f KB." % (max_size))

	f = open(payload, "rb")
	data = f.read()
	f.close()
	print("[+] Payload size: %.3f KB " % (len(data)/1024.0))
		
	# Encrypt
	data_enc = encrypt_input(data, password)

	# Process data from payload file
	v = decompose(data_enc)
	
	# Add until multiple of 3
	while(len(v)%3):
		v.append(0)

	payload_size = len(v)/8/1024.0
	print("[+] Encrypted payload size: %.3f KB " % (payload_size))
	if (payload_size > max_size - 4):
		print("[-] Cannot embed. File too large")
		sys.exit()
		
	# Create output image
	steg_img = Image.new('RGBA',(width, height))
	data_img = steg_img.getdata()

	idx = 0

	for h in range(height):
		for w in range(width):
			(r, g, b, a) = conv.getpixel((w, h))
			if idx < len(v):
				r = set_bit(r, 0, v[idx])
				g = set_bit(g, 0, v[idx+1])
				b = set_bit(b, 0, v[idx+2])
			data_img.putpixel((w,h), (r, g, b, a))
			idx = idx + 3
    
	steg_img.save(imgFile + "-stego.png", "PNG")
	
	print("[+] %s embedded successfully!" % payload)

# Extract data embedded into LSB of the input file
def extract(in_file, out_file, password):
	# Process source image
	img = Image.open(in_file)
	(width, height) = img.size
	conv = img.convert("RGBA").getdata()
	print("[+] Image size: %dx%d pixels." % (width, height))

	# Extract LSBs
	v = []
	for h in range(height):
		for w in range(width):
			(r, g, b, a) = conv.getpixel((w, h))
			v.append(r & 1)
			v.append(g & 1)
			v.append(b & 1)
			
	data_out = assemble(v)
	
	# Decrypt
	data_dec = decrypt_input(data_out, password)

	# Write decrypted data
	out_f = open(out_file, "wb")
	out_f.write(data_dec)
	out_f.close()
	
	print("[+] Written extracted data to %s." % out_file)

# Statistical analysis of an image to detect LSB steganography
def analyse(in_file):
	'''
	- Split the image into blocks.
	- Compute the average value of the LSBs for each block.
	- The plot of the averages should be around 0.5 for zones that contain
	  hidden encrypted messages (random data).
	'''
	BS = 100	# Block size 
	img = Image.open(in_file)
	(width, height) = img.size
	print("[+] Image size: %dx%d pixels." % (width, height))
	conv = img.convert("RGBA").getdata()

	# Extract LSBs
	vr = []	# Red LSBs
	vg = []	# Green LSBs
	vb = []	# LSBs
	for h in range(height):
		for w in range(width):
			(r, g, b, a) = conv.getpixel((w, h))
			vr.append(r & 1)
			vg.append(g & 1)
			vb.append(b & 1)

	# Average colours' LSB per each block
	avgR = []
	avgG = []
	avgB = []
	for i in range(0, len(vr), BS):
		avgR.append(numpy.mean(vr[i:i + BS]))
		avgG.append(numpy.mean(vg[i:i + BS]))
		avgB.append(numpy.mean(vb[i:i + BS]))

	# Nice plot 
	numBlocks = len(avgR)
	blocks = [i for i in range(0, numBlocks)]
	plt.axis([0, len(avgR), 0, 1])
	plt.ylabel('Average LSB per block')
	plt.xlabel('Block number')

#	plt.plot(blocks, avgR, 'r.')
#	plt.plot(blocks, avgG, 'g')
	plt.plot(blocks, avgB, 'bo')
	
	plt.show()

def usage(progName):
	print("LSB steganogprahy. Hide files within least significant bits of images.\n")
	print("Usage:")
	print("  %s hide <img_file> <payload_file> <password>" % progName)
	print("  %s extract <stego_file> <out_file> <password>" % progName)
	print("  %s analyse <stego_file>" % progName)
	sys.exit()
	
if __name__ == "__main__":
	if len(sys.argv) < 3:
		usage(sys.argv[0])
		
	if sys.argv[1] == "hide":		
		embed(sys.argv[2], sys.argv[3], sys.argv[4])
	elif sys.argv[1] == "extract":
		extract(sys.argv[2], sys.argv[3], sys.argv[4])
	elif sys.argv[1] == "analyse":
		analyse(sys.argv[2])
	else:
		print("[-] Invalid operation specified")
