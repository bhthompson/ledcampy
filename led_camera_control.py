#! /usr/bin/python
# LED control script using a USB camera interface.
# This depends on the ledconpy led_control package.

import argparse
import atexit
import cv, cv2
import led_array
import logging
import sys

_CAMERA_FRAME_W = 352
_CAMERA_FRAME_H = 288

def scale_to_pwm(r, g, b, pwm_max):
  """Scale the RGB value to within the maximum PWM value."""
  max_rgb = max([r, g, b])
  scale_factor = pwm_max / float(max_rgb)
  logging.debug('Found max color value of %d, scaling to %d with %f',
                max_rgb, pwm_max, scale_factor)
  r_scaled = r * scale_factor
  g_scaled = g * scale_factor
  b_scaled = b * scale_factor
  logging.debug('Scaled R:%d, G:%d, B:%d', r_scaled, g_scaled, b_scaled) 
  return (r_scaled, g_scaled, b_scaled)

def main():
  parser = argparse.ArgumentParser(description='Camera LED control script',
             formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('-v', '--verbose', action='count')
  parser.add_argument('-t', '--test', action='store_true',
                      help='Run a basic test sequence.')
  parser.add_argument('-f', '--filename', default=None, type=str,
                      help='File containing a LED sequence.')
  parser.add_argument('--red_pin_name', default="P8_13", type=str,
                      help='Name of the red PWM pin.')
  parser.add_argument('--green_pin_name', default="P8_19", type=str,
                      help='Name of the green PWM pin.')
  parser.add_argument('--blue_pin_name', default="P9_14", type=str,
                      help='Name of the blue PWM pin.')
  parser.add_argument('--pwm_max_value', default=100, type=int,
                      help='Max value the PWM driver will accept.')
  args = parser.parse_args()
  logging.basicConfig(format='%(levelname)s:%(message)s', 
                      level=logging.WARNING - 10 * (args.verbose or 0))

  array = led_array.LedArray(args.red_pin_name, args.green_pin_name,
                                 args.blue_pin_name, args.pwm_max_value)
  atexit.register(array.__exit__)

  cam = cv2.VideoCapture(0)
  if not cam.isOpened():
    logging.error('Failed to initialize camera.')
    sys.exit()
  cam.set(cv.CV_CAP_PROP_FRAME_WIDTH, _CAMERA_FRAME_W)
  cam.set(cv.CV_CAP_PROP_FRAME_HEIGHT, _CAMERA_FRAME_H)

  retval, image = cam.read()
  if not retval:
    logging.warning('Failed to read from camera.')

  if args.test:
    logging.info('Saving a test camera capture to test.png.')
    cv.SaveImage('test.png', cv.fromarray(image))
    logging.info('Running basic RGB LED test.')
    array.test_colors(1.0)
    sys.exit()

  while(1):
    # Just pick an arbitrary pixel in the middle for now.
    r = image[175, 144, 0]
    g = image[175, 144, 1]
    b = image[175, 144, 2]
    logging.debug('R: %d, G: %d, B: %d', r, g, b)
    r_scaled, g_scaled, b_scaled = scale_to_pwm(r, g, b, args.pwm_max_value)
    array.set_rgb(r_scaled, g_scaled, b_scaled)
    retval, image = cam.read()
    if not retval:
      logging.warning('Failed to read from camera.')

main()
