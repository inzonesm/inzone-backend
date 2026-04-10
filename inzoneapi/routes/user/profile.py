# routes/user/profile.py
from flask import Blueprint, request, jsonify
from services.user.profile_service import ProfileService

user_profile_bp = Blueprint('user_profile', __name__)

@user_profile_bp.route('/user/update-name', methods=['POST'])
def update_name():
    try:
        data = request.get_json()
        # ProfileService methods return (response, status_code) tuples
        return ProfileService.update_name(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@user_profile_bp.route('/user/create-profile', methods=['POST'])
def create_profile():
    try:
        data = request.get_json()
        return ProfileService.create_profile(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/update-username', methods=['POST'])
def update_username():
    try:
        data = request.get_json()
        return ProfileService.update_username(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.get_json()
        return ProfileService.update_profile(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/update-profile-picture', methods=['POST'])
def update_profile_picture():
    try:
        data = request.get_json()
        return ProfileService.update_profile_picture(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/update-bio', methods=['POST'])
def update_bio():
    try:
        data = request.get_json()
        return ProfileService.update_bio(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/update-interests', methods=['POST'])
def update_interests():
    try:
        data = request.get_json()
        return ProfileService.update_interests(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/get-profile', methods=['GET'])
def get_profile():
    try:
        return ProfileService.get_profile({})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/follow', methods=['POST'])
def follow():
    try:
        data = request.get_json()
        return ProfileService.follow(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/unfollow', methods=['POST'])
def unfollow():
    try:
        data = request.get_json()
        return ProfileService.unfollow(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/remove-from-following', methods=['POST'])
def remove_from_following():
    try:
        data = request.get_json()
        return ProfileService.remove_from_following(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/remove-from-followers', methods=['POST'])
def remove_from_followers():
    try:
        data = request.get_json()
        return ProfileService.remove_from_followers(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@user_profile_bp.route('/feedback', methods=['POST'])
def send_feedback():
    try:
        data = request.get_json()
        return ProfileService.send_feedback(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/like-post', methods=['POST'])
def like_post():
    try:
        data = request.get_json()
        return ProfileService.like_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/unlike-post', methods=['POST'])
def unlike_post():
    try:
        data = request.get_json()
        return ProfileService.unlike_post(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/get-liked-posts', methods=['POST'])
def get_liked_posts():
    try:
        data = request.get_json()
        return ProfileService.get_liked_posts(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/generate-referral-code', methods=['POST'])
def generate_referral_code():
    try:
        data = request.get_json()
        return ProfileService.generate_referral_code(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/apply-referral', methods=['POST'])
def apply_referral():
    try:
        data = request.get_json()
        return ProfileService.apply_referral(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

def grant_referral_rewards(referrer_id, referee_id):
    try:
        data = request.get_json()
        return ProfileService.grant_referral_rewards(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@user_profile_bp.route('/user/referral-stats', methods=['GET'])
def get_referral_stats():
    try:
        return ProfileService.get_referral_stats({})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
