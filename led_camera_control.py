#! /usr/bin/python
# LED control script using a USB camera interface.
# This depends on the ledconpy led_array package.

import argparse
import atexit
import cv, cv2
import led_array
import logging
import sys

_CAMERA_FRAME_W = 160
_CAMERA_FRAME_H = 120

class CameraProcessor:
  """Camera processing mechanisms for finding values to control RGB LEDs."""
  def average_of_region(self, image, v_start = .25, v_end = .75, h_start = .25,
                        h_end = .75):
    """Find the average RGB values for a region of an image, the region is
    defined by relative fractions into the image."""
    if v_start > v_end or h_start > h_end or v_end > 1 or h_end > 1:
      logging.error('Invalid region parameters! v_start: %f, v_end: %f, '
                    'h_start: %f, h_end: %f', v_start, v_end, h_start, h_end)
      return
    (v, h, c) = image.shape
    if c != 3:
      logging.error('Image is not 3 channel, only BGR numpy array supported.')
      return
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

  def scale_to_pwm(self, r, g, b, pwm_max):
    """Scale the RGB value to within the maximum PWM value."""
    #Widen the scaling so the lowest value is effectively minimized.
    #This promotes more colorful colors, and avoids 'white'.
    min_rgb = min([r, g, b])
    r = r - min_rgb + 1
    g = g - min_rgb + 1
    b = b - min_rgb + 1
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

  cam_processor = CameraProcessor()

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
    r, g, b = cam_processor.average_of_region(image)
    r_scaled, g_scaled, b_scaled = cam_processor.scale_to_pwm(
                                     r, g, b, args.pwm_max_value)
    array.set_rgb(r_scaled, g_scaled, b_scaled)
    #array.fade(r_scaled, g_scaled, b_scaled, .01)
    retval, image = cam.read()
    if not retval:
      logging.warning('Failed to read from camera.')

main()
