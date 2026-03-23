const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');

// Initialize Firebase Admin
admin.initializeApp();
const db = admin.firestore();

/**
 * Cloud Function that triggers when a document in the groupChats collection is updated
 * Specifically responds when new messages are added
 */
exports.add_ai_message_on_update = functions.firestore
  .document('groupChats/{groupChatId}')
  .onUpdate(async (change, context) => {
    // Get the data before and after the update
    const beforeData = change.before.data();
    const afterData = change.after.data();
    const groupChatId = context.params.groupChatId;

    // Extract messages from before and after
    const beforeMessages = beforeData.messages || [];
    const afterMessages = afterData.messages || [];
    
    // If no new messages were added, exit early
    if (afterMessages.length <= beforeMessages.length) {
      console.log('No new messages detected, exiting early.');
      return null;
    }

    // Get the last processed message ID
    const lastProcessedMessageId = beforeData.lastProcessedMessageId || '';
    
    // Find new messages that need processing
    let newMessages = [];
    if (lastProcessedMessageId) {
      // Find where the last processed message is in the list
      const lastIdx = afterMessages.findIndex(m => m.id === lastProcessedMessageId);
      if (lastIdx >= 0) {
        newMessages = afterMessages.slice(lastIdx + 1);
      } else {
        // If the last processed message is not found, process all messages
        // This shouldn't happen in normal operation
        newMessages = afterMessages;
      }
    } else {
      newMessages = afterMessages;
    }
    
    // Only continue if there are new messages and the last message is from a user
    const lastMessage = newMessages[newMessages.length - 1];
    if (!lastMessage || lastMessage.sender?.type !== 'user') {
      console.log('Last message is not from a user or no new messages, exiting.');
      return null;
    }
    
    console.log(`Processing ${newMessages.length} new messages in chat ${groupChatId}`);
    
    // Get AI participants from the group chat
    const aiParticipants = (afterData.participants || []).filter(p => p.type === 'ai');
    
    if (!aiParticipants.length) {
      console.log('No AI participants in this chat');
      return null;
    }
    
    try {
      // Get the last 5 messages for context
      const lastFiveMessages = afterMessages.slice(Math.max(0, afterMessages.length - 5));
      
      // Call our AI service to generate responses
      const aiResponses = await generateAIResponses(lastFiveMessages, aiParticipants);
      
      if (!aiResponses || !aiResponses.length) {
        console.log('No AI responses generated');
        return null;
      }
      
      // Append AI responses to the messages
      const updatedMessages = [...afterMessages, ...aiResponses];
      
      // Update the document with new messages and last processed message ID
      return db.collection('groupChats').doc(groupChatId).update({
        messages: updatedMessages,
        lastProcessedMessageId: aiResponses[aiResponses.length - 1].id,
        updatedAt: admin.firestore.FieldValue.serverTimestamp()
      });
    } catch (error) {
      console.error('Error generating AI responses:', error);
      throw new functions.https.HttpsError('internal', 'Failed to generate AI responses', error);
    }
  });

/**
 * Generate AI responses using the orchestrator service
 * This could call your Python orchestrator service or use a JavaScript implementation
 */
async function generateAIResponses(messages, aiParticipants) {
  // Option 1: Call your Python orchestrator API (if you have it running as a service)
  // In a production environment, you'd want to deploy your Python code as a microservice
  
  /*
  try {
    const response = await axios.post('http://your-orchestrator-api/generate-responses', {
      messages,
      aiParticipants
    });
    return response.data.responses;
  } catch (error) {
    console.error('Error calling orchestrator API:', error);
    throw error;
  }
  */
  
  // Option 2: Simple implementation for demonstration purposes
  // This is a placeholder that should be replaced with your actual logic
  
  const responses = [];
  // Get the last user message
  const lastUserMessage = messages.find(m => m.sender?.type === 'user');
  
  if (!lastUserMessage) return responses;
  
  // For each AI participant, decide if they should respond
  // In reality, this should use your orchestrator logic
  for (const ai of aiParticipants) {
    // In a real implementation, this would use your orchestration logic
    // to decide which AIs respond and what they say
    
    // Simple example response
    responses.push({
      id: getCurrentTimestamp() + uuidv4().substring(0, 8),
      sender: {
        uid: ai.uid,
        name: ai.name,
        type: 'ai'
      },
      content: `This is a placeholder response from ${ai.name}. In production, this would use the Python orchestrator logic.`,
      isProcessed: true
    });
  }
  
  return responses;
}

/**
 * Get current timestamp in the format 'YYYYMMDDHHmmss'
 */
function getCurrentTimestamp() {
  const now = new Date();
  return now.getFullYear() +
    String(now.getMonth() + 1).padStart(2, '0') +
    String(now.getDate()).padStart(2, '0') +
    String(now.getHours()).padStart(2, '0') +
    String(now.getMinutes()).padStart(2, '0') +
    String(now.getSeconds()).padStart(2, '0');
}