# routes/groups/management.py
from flask import Blueprint, request, jsonify
from services.groups.chat_service import GroupChatService

groups_mgmt_bp = Blueprint('groups_mgmt', __name__)


@groups_mgmt_bp.route('/group/add-participant', methods=['POST'])
def add_participant():
    """Add a participant to a group chat"""
    try:
        data = request.json
        return GroupChatService.add_participant(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_mgmt_bp.route('/group/delete-participant', methods=['POST'])
def delete_participant():
    """Remove a participant from a group chat"""
    try:
        data = request.json
        return GroupChatService.delete_participant(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_mgmt_bp.route('/group/create-groupchat', methods=['POST'])
def create_group_chat():
    """Create a new group chat"""
    try:
        data = request.json
        return GroupChatService.create_groupchat(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_mgmt_bp.route('/group/add-ai-character', methods=['POST'])
def add_ai_character():
    """Add an AI character to a group chat"""
    try:
        data = request.json
        return GroupChatService.add_ai_character(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@groups_mgmt_bp.route('/group/delete-ai-character', methods=['POST'])
def delete_ai_character():
    """Remove an AI character from a group chat"""
    try:
        data = request.json
        return GroupChatService.delete_ai_character(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
