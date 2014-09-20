#! /usr/bin/python
# LED control script using a USB camera interface.
# This depends on the ledconpy led_array package.

import argparse
import cv, cv2
import led_array
import logging
import signal
import sys
import threading
import time

_CAMERA_FRAME_W = 160
_CAMERA_FRAME_H = 120

class CameraProcessor:
  """Camera processing mechanisms for finding values to control RGB LEDs."""
  def __init__(self, pwm_max, r_bal = 1.0, g_bal = 1.0, b_bal = 1.0):
    assert 0 <= r_bal <= 1, 'invalid R balance value: %f' % r_bal
    assert 0 <= g_bal <= 1, 'invalid G balance value: %f' % g_bal
    assert 0 <= b_bal <= 1, 'invalid B balance value: %f' % b_bal
    self.cam = cv2.VideoCapture(0)
    assert self.cam.isOpened(), 'failed to open the camera capture interface'
    self.cam.set(cv.CV_CAP_PROP_FRAME_WIDTH, _CAMERA_FRAME_W)
    self.cam.set(cv.CV_CAP_PROP_FRAME_HEIGHT, _CAMERA_FRAME_H)
    self.last_r = 0
    self.last_g = 0
    self.last_b = 0
    self.r_balance = r_bal
    self.g_balance = g_bal
    self.b_balance = b_bal
    self.pwm_max = pwm_max

  def average_and_scale(self, image):
    r, g, b = self.average_of_region(image)
    r, g, b = self.color_balance(r, g, b)
    return self.scale_to_pwm(r, g, b)

  def average_of_region(self, image, v_start = .25, v_end = .75, h_start = .25,
                        h_end = .75):
    """Find the average RGB values for a region of an image, the region is
    defined by relative fractions into the image."""
    assert v_start < v_end and h_start < h_end, \
      'region must be defined positively'
    assert 0 <= v_start <= 1 and 0 <= v_end <= 1, \
      'vertical region must be defined with fractions'
    assert 0 <= h_start <= 1 and 0 <= h_end <= 1, \
      'horizontal region must be defined with fractions'
    (v, h, c) = image.shape
    assert c == 3, 'Image must be 3 channel, only BGR numpy array supported.'
    # Be warned, there is a reasonable chance of overflowing here, so
    # we use long variables.
    r_sum = long(0)
    g_sum = long(0)
    b_sum = long(0)
    region = image[(v * v_start):(v * v_end), (h * h_start):(h * h_end)]
    for v_pix in range(region.shape[0]):
      for h_pix in range(region.shape[1]):
        #BGR ordering
        r_sum = r_sum + image[h_pix, v_pix, 2]
        g_sum = g_sum + image[h_pix, v_pix, 1]
        b_sum = b_sum + image[h_pix, v_pix, 0]
    r_avg = r_sum / region.size
    g_avg = g_sum / region.size
    b_avg = b_sum / region.size
    logging.debug('Using image dimensions of: %dx%d @%dbpp', h, v, c)
    logging.debug('r_sum: %d, g_sum: %d, b_sum:%d, total sampled: %d', r_sum,
                  g_sum, b_sum, region.size)
    logging.debug('Average R: %d, G: %d, B: %d', r_avg, g_avg, b_avg)
    return (r_avg, g_avg, b_avg)

  def capture_image(self):
    retval, image = self.cam.read()
    if not retval:
      logging.warning('Failed to read from camera.')
    return image

  def color_balance(self, r, g, b):
    """Balance the colors by scaling down the overly predominant colors
    which the camera generates."""
    r_corrected = r * self.r_balance
    g_corrected = g * self.g_balance
    b_corrected = b * self.b_balance
    logging.debug('Colors Balanced R: %d, G: %d, B: %d', r_corrected,
                  g_corrected, b_corrected)
    return (r_corrected, g_corrected, b_corrected)

  def scale_to_pwm(self, r, g, b):
    """Scale the RGB value to within the maximum PWM value."""
    #Widen the scaling so the lowest value is effectively minimized.
    #This promotes more colorful colors, and avoids 'white'.
    min_rgb = min([r, g, b])
    r = r - min_rgb + 1
    g = g - min_rgb + 1
    b = b - min_rgb + 1
    max_rgb = max([r, g, b])
    scale_factor = self.pwm_max / float(max_rgb)
    logging.debug('Found max color value of %d, scaling to %d with %f',
                  max_rgb, self.pwm_max, scale_factor)
    r_scaled = r * scale_factor
    g_scaled = g * scale_factor
    b_scaled = b * scale_factor
    logging.debug('Scaled R:%d, G:%d, B:%d', r_scaled, g_scaled, b_scaled)
    return (r_scaled, g_scaled, b_scaled)

class ControlThreads:
  """Control threads which need to share state information."""
  def __init__(self, cam_processor, array, exit_event):
    self.cam_processor = cam_processor
    self.array = array
    self.exit_event = exit_event
    self.r = 0
    self.g = 0
    self.b = 0

  def cam_thread_func(self):
    #TODO: find some way to determine when we should be off.
    while(1):
      image = self.cam_processor.capture_image()
      self.r, self.g, self.b = self.cam_processor.average_and_scale(image)
      if self.exit_event.is_set():
        logging.debug('cam_thread_func: exit event caught.')
        self.array.__exit__()
        break

  def led_thread_func(self):
    while(1):
      #TODO: take an event from the camera thread to start the fade
      #transitions within a maximum rate of change.
      self.array.fade(self.r, self.g, self.b, .1)
      if self.exit_event.is_set():
        logging.debug('led_thread_func: exit event caught.')
        break

def main():
  def exit_handler(signal, frame):
    exit_event.set()
    logging.debug('Exit event set, main is exiting.')
    sys.exit()

  parser = argparse.ArgumentParser(description='Camera LED control script',
             formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('-v', '--verbose', action='count')
  parser.add_argument('-t', '--test', action='store_true',
                      help='Run a basic test sequence.')
  parser.add_argument('--red_pin_name', default="P8_13", type=str,
                      help='Name of the red PWM pin.')
  parser.add_argument('--green_pin_name', default="P8_19", type=str,
                      help='Name of the green PWM pin.')
  parser.add_argument('--blue_pin_name', default="P9_14", type=str,
                      help='Name of the blue PWM pin.')
  parser.add_argument('--pwm_max_value', default=100, type=int,
                      help='Max value the PWM driver will accept.')
  parser.add_argument('--red_balance', default=1.0, type=float,
                      help='Red balance (0 - 1.0).')
  parser.add_argument('--green_balance', default=1.0, type=float,
                      help='Green balance (0 - 1.0).')
  parser.add_argument('--blue_balance', default=0.9, type=float,
                      help='Blue balance (0 - 1.0).')
  args = parser.parse_args()

  logging.basicConfig(format='%(levelname)s:%(message)s', 
                      level=logging.WARNING - 10 * (args.verbose or 0))
  array = led_array.LedArray(args.red_pin_name, args.green_pin_name,
                                 args.blue_pin_name, args.pwm_max_value)
  cam_processor = CameraProcessor(args.pwm_max_value, args.red_balance,
                                  args.green_balance, args.blue_balance)

  if args.test:
    image = cam_processor.capture_image()
    logging.info('Saving a test camera capture to test.png.')
    cv.SaveImage('test.png', cv.fromarray(image))
    logging.info('Running basic RGB LED test.')
    array.test_colors(1.0)
    array.__exit__()
    sys.exit()

  exit_event = threading.Event()
  control_threads = ControlThreads(cam_processor, array, exit_event)
  signal.signal(signal.SIGINT, exit_handler)
  led_thread = threading.Thread(target=control_threads.led_thread_func)
  cam_thread = threading.Thread(target=control_threads.cam_thread_func)
  cam_thread.start()
  led_thread.start()

  while(1):
    #Main is basicaly done, we just keep alive so we can notify the threads
    #if an exit condition is detected.
    time.sleep(.5)
    if exit_event.is_set():
      exit_handler()
      break

main()
