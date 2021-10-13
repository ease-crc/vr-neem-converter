from symbol import atom
from typing import List


def pose_to_knowrob_string(pose: List[float], reference_frame="world") -> str:
    """
    Convert a pq list [x,y,z,qx,qy,qz,qw] to a KnowRob pose "[reference_cs, [x,y,z],[qx,qy,qz,qw]]"
    """
    return f"[{atom(reference_frame)}, [{pose[0]},{pose[1]},{pose[2]}], [{pose[3]},{pose[4]},{pose[5]},{pose[6]}]]"

