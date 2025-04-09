# test_bot.py

import pytest
import pytest_asyncio # Implicitly used by pytest.mark.asyncio
from unittest.mock import AsyncMock, MagicMock, patch # Use AsyncMock for awaitables
import requests
import os

# Import the command object from your bot code and alias it for clarity
# Assuming your bot file is named bot.py
from bot import attribute_speakers as attribute_speakers_command

# --- Fixtures ---

@pytest.fixture
def mock_interaction(mocker):
    """Fixture to create a mock discord.Interaction object."""
    # Create a base mock for the interaction
    mock_interaction = MagicMock() # Use MagicMock to allow arbitrary attribute access

    # Mock the nested response object and its methods using AsyncMock for awaitables
    mock_interaction.response = AsyncMock()
    mock_interaction.response.defer = AsyncMock()
    mock_interaction.response.send_message = AsyncMock()

    # Mock the nested followup object and its methods
    mock_interaction.followup = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    # Mock the user attribute (optional, but good practice)
    mock_interaction.user = MagicMock()
    mock_interaction.user.name = "TestUser"
    mock_interaction.user.id = 12345

    return mock_interaction

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Fixture to set mock environment variables for tests."""
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "http://test-n8n-instance.com")
    # DISCORD_BOT_TOKEN is not directly used in the command, so mocking N8N_URL is sufficient here
    # If other commands used the token, you'd mock it too.

# --- Test Cases ---

@pytest.mark.asyncio
async def test_attribute_speakers_success(mock_interaction, mocker):
    """Test the command with valid input and a successful webhook call."""
    # Arrange
    execution_id = "exec_123"
    metadata_str = "speaker_00:Alice, speaker_01:Bob " # Include space variations
    transcription_id = "trans_abc"
    expected_webhook_url = f"http://localhost:5678/webhook-waiting/{execution_id}"
    expected_payload = {
        "metadata": {"speaker_00": "Alice", "speaker_01": "Bob"},
        "transcription_id": transcription_id
    }
    # Mock requests.post to return a successful response
    mock_post = mocker.patch('requests.post', return_value=MagicMock(status_code=200, raise_for_status=lambda: None))

    # Act --- Call the function's CALLBACK under test ---
    await attribute_speakers_command.callback(mock_interaction, execution_id, metadata_str, transcription_id)

    # Assert ---
    # 1. Check if defer was called
    mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    # 2. Check if requests.post was called correctly
    mock_post.assert_called_once_with(
        expected_webhook_url,
        json=expected_payload,
        timeout=10
    )
    # 3. Check if the success message was sent via followup
    mock_interaction.followup.send.assert_awaited_once_with(
        f"✅ Successfully sent metadata for execution `{execution_id}` to the workflow!",
        ephemeral=True
    )
    # 4. Ensure the error response wasn't called
    mock_interaction.response.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_attribute_speakers_invalid_metadata_format(mock_interaction, mocker):
    """Test the command with improperly formatted metadata."""
    # Arrange
    execution_id = "exec_456"
    invalid_metadata_str = "speaker_00:Alice, speaker_01Bob" # Missing colon
    transcription_id = "trans_def"
    # Mock requests.post just in case, although it shouldn't be called
    mock_post = mocker.patch('requests.post')

    # Act --- Call the function's CALLBACK under test ---
    await attribute_speakers_command.callback(mock_interaction, execution_id, invalid_metadata_str, transcription_id)

    # Assert ---
    # 1. Check if the specific error message was sent via response.send_message
    mock_interaction.response.send_message.assert_awaited_once_with(
        "❌ Invalid metadata format. Please use format 'speaker_00:name,speaker_01:name'",
        ephemeral=True
    )
    # 2. Ensure defer and followup were NOT called
    mock_interaction.response.defer.assert_not_awaited()
    mock_interaction.followup.send.assert_not_awaited()
    # 3. Ensure requests.post was NOT called
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_attribute_speakers_webhook_404_error(mock_interaction, mocker):
    """Test the command when the webhook returns a 404 Not Found."""
    # Arrange
    execution_id = "exec_789"
    metadata_str = "speaker_02:Charlie"
    transcription_id = "trans_ghi"
    expected_webhook_url = f"http://test-n8n-instance.com/webhook-waiting/{execution_id}"
    # Configure the mock response for 404
    mock_response = MagicMock(status_code=404, text="Execution not found or already completed")
    # Make raise_for_status raise an appropriate error when called
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_post = mocker.patch('requests.post', return_value=mock_response)

    # Act --- Call the function's CALLBACK under test ---
    await attribute_speakers_command.callback(mock_interaction, execution_id, metadata_str, transcription_id)

    # Assert ---
    # 1. Check defer was called
    mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    # 2. Check requests.post was called
    mock_post.assert_called_once() # Args already checked in success test, focus on outcome
    # 3. Check if the specific 404 error message was sent via followup
    expected_error_msg_part1 = f"❌ Failed to send metadata to the workflow for execution `{execution_id}`."
    expected_error_msg_part2 = f"\n_Details: Received status 404 from n8n._"
    expected_error_msg_part3 = "\n_(This often means the execution ID is incorrect or the workflow is no longer waiting.)_"
    # Check if the actual message contains all expected parts
    call_args, call_kwargs = mock_interaction.followup.send.call_args
    actual_message = call_args[0]
    assert expected_error_msg_part1 in actual_message
    assert expected_error_msg_part2 in actual_message
    assert expected_error_msg_part3 in actual_message
    # Also check ephemeral=True
    assert call_kwargs['ephemeral'] is True


@pytest.mark.asyncio
async def test_attribute_speakers_webhook_connection_error(mock_interaction, mocker):
    """Test the command when requests.post fails to connect."""
    # Arrange
    execution_id = "exec_101"
    metadata_str = "speaker_03:David"
    transcription_id = "trans_jkl"
    # Configure mock_post to raise a ConnectionError
    mock_post = mocker.patch('requests.post', side_effect=requests.exceptions.ConnectionError("Failed to establish connection"))

    # Act --- Call the function's CALLBACK under test ---
    await attribute_speakers_command.callback(mock_interaction, execution_id, metadata_str, transcription_id)

    # Assert ---
    # 1. Check defer was called
    mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    # 2. Check requests.post was called
    mock_post.assert_called_once()
    # 3. Check if the specific connection error message was sent via followup
    expected_error_msg_part1 = f"❌ Failed to send metadata to the workflow for execution `{execution_id}`."
    expected_error_msg_part2 = "\n_(Could not connect to the n8n instance.)_"
    call_args, call_kwargs = mock_interaction.followup.send.call_args
    actual_message = call_args[0]
    assert expected_error_msg_part1 in actual_message
    assert expected_error_msg_part2 in actual_message
    assert call_kwargs['ephemeral'] is True


@pytest.mark.asyncio
async def test_attribute_speakers_unexpected_error(mock_interaction, mocker):
    """Test handling of an unexpected error during processing."""
    # Arrange
    execution_id = "exec_err"
    metadata_str = "speaker_04:Eve"
    transcription_id = "trans_mno"
    # Mock requests.post to cause an unexpected error *after* defer()
    mocker.patch('requests.post', side_effect=ValueError("Something weird happened")) # Simulate unexpected error

    # Act --- Call the function's CALLBACK under test ---
    await attribute_speakers_command.callback(mock_interaction, execution_id, metadata_str, transcription_id)

    # Assert ---
    # 1. Check defer was called
    mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    # 2. Check that the generic error message was sent
    mock_interaction.followup.send.assert_awaited_once_with(
        f"❌ An unexpected error occurred. Please check the bot logs.",
        ephemeral=True
    )