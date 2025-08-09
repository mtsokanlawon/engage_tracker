import math
import numpy as np
import cv2

def euclidean_distance(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def get_eye_aspect_ratio(eye_landmarks):
    A = euclidean_distance(eye_landmarks[1], eye_landmarks[5])
    B = euclidean_distance(eye_landmarks[2], eye_landmarks[4])
    C = euclidean_distance(eye_landmarks[0], eye_landmarks[3])
    return (A+B) / (2.0*C) if C != 0 else 0

def get_mouth_aspect_ratio(mouth_landmarks):
    A = euclidean_distance(mouth_landmarks[1], mouth_landmarks[5])
    B = euclidean_distance(mouth_landmarks[2], mouth_landmarks[4])
    C = euclidean_distance(mouth_landmarks[0], mouth_landmarks[3])
    return (A+B) / (2.0*C) if C != 0 else 0

def get_head_pose(face_landmarks, image_shape):
    img_h, img_w, _ = image_shape
    image_points = np.array([
        (face_landmarks[1].x * img_w, face_landmarks[1].y * img_h),
        (face_landmarks[152].x * img_w, face_landmarks[152].y * img_h),
        (face_landmarks[33].x * img_w, face_landmarks[33].y * img_h),
        (face_landmarks[263].x * img_w, face_landmarks[263].y * img_h),
        (face_landmarks[61].x * img_w, face_landmarks[61].y * img_h),
        (face_landmarks[291].x * img_w, face_landmarks[291].y * img_h)
    ], dtype="double")
    model_points = np.array([
        (0.0, 0.0, 0.0),
        (0.0, -330.0, -65.0),
        (-225.0, 170.0, -135.0),
        (225.0, 170.0, -135.0),
        (-150.0, -150.0, -125.0),
        (150.0, -150.0, -125.0)
    ])
    focal_length = img_w
    center = (img_w / 2, img_h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype="double")
    dist_coeffs = np.zeros((4, 1))
    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)
    rmat, _ = cv2.Rodrigues(rotation_vector)
    angles, *_ = cv2.RQDecomp3x3(rmat)
    return angles[0], angles[1], angles[2]
