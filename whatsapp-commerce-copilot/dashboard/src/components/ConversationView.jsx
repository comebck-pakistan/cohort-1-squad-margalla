import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { API_URL } from '../config';
import { Bot, User, Phone, CheckCircle2, AlertCircle } from 'lucide-react';

const ConversationView = ({ storeId }) => {
  const [conversations, setConversations] = useState([]);
  const [selectedConvId, setSelectedConvId] = useState(null);
  const [convDetails, setConvDetails] = useState(null);
  const [messageInput, setMessageInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);

  // Fetch conversations list
  useEffect(() => {
    const fetchConvs = async () => {
      try {
        const res = await axios.get(`${API_URL}/stores/${storeId}/conversations`);
        setConversations(res.data);
      } catch (err) {
        console.error('Failed to load conversations', err);
      }
    };
    fetchConvs();
    const interval = setInterval(fetchConvs, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [storeId]);

  // Fetch selected conversation
  useEffect(() => {
    if (!selectedConvId) {
      setConvDetails(null);
      return;
    }
    
    const fetchDetails = async () => {
      try {
        const res = await axios.get(`${API_URL}/stores/${storeId}/conversations/${selectedConvId}`);
        setConvDetails(res.data);
        scrollToBottom();
      } catch (err) {
        console.error('Failed to load conversation details', err);
      }
    };
    
    fetchDetails();
    const interval = setInterval(fetchDetails, 3000); // Poll fast for selected
    return () => clearInterval(interval);
  }, [selectedConvId, storeId]);

  const scrollToBottom = () => {
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  const handleToggleAI = async (currentIsAI) => {
    try {
      const endpoint = currentIsAI ? 'takeover' : 'enable-ai';
      await axios.post(`${API_URL}/stores/${storeId}/conversations/${selectedConvId}/${endpoint}`);
      // Optimistic update
      setConvDetails({ ...convDetails, is_ai_controlled: !currentIsAI });
      setConversations(conversations.map(c => 
        c.id === selectedConvId ? { ...c, is_ai_controlled: !currentIsAI } : c
      ));
    } catch (err) {
      console.error('Failed to toggle AI mode', err);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!messageInput.trim() || isSending) return;

    setIsSending(true);
    try {
      await axios.post(`${API_URL}/stores/${storeId}/conversations/${selectedConvId}/send`, {
        message: messageInput.trim()
      });
      setMessageInput('');
      
      // Force a quick poll to show the message instantly
      const res = await axios.get(`${API_URL}/stores/${storeId}/conversations/${selectedConvId}`);
      setConvDetails(res.data);
      scrollToBottom();
    } catch (err) {
      console.error('Failed to send message', err);
      alert('Failed to send message. Please try again.');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%' }}>
      {/* Left List */}
      <div style={{ width: '300px', borderRight: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Active Chats</h3>
        </div>
        
        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
          {conversations.length === 0 ? (
            <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
              No active conversations. Send a message to the WhatsApp number to start.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {conversations.map(conv => (
                <li key={conv.id}>
                  <button
                    onClick={() => setSelectedConvId(conv.id)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '0.75rem',
                      background: selectedConvId === conv.id ? 'var(--bg-panel-hover)' : 'transparent',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.5rem'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>+{conv.customer_phone || 'Unknown'}</span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        {new Date(conv.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', color: conv.is_ai_controlled ? 'var(--success)' : '#F59E0B', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        {conv.is_ai_controlled ? <><Bot size={12}/> AI Managed</> : <><User size={12}/> Human</>}
                      </span>
                      {conv.order_stage !== 'BROWSING' && (
                        <span style={{ fontSize: '0.65rem', background: 'var(--accent-primary)', padding: '0.1rem 0.4rem', borderRadius: '4px', color: '#fff' }}>
                          {conv.order_stage}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Right Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-main)' }}>
        {selectedConvId && convDetails ? (
          <>
            {/* Header */}
            <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-panel)' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Phone size={16} color="var(--text-secondary)" /> +{convDetails.customer_phone || 'Unknown'}
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                  Order Stage: {convDetails.order_stage}
                </p>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-panel-hover)', padding: '0.4rem 0.8rem', borderRadius: '20px', border: '1px solid var(--border-color)' }}>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Control:</span>
                  <button 
                    onClick={() => handleToggleAI(convDetails.is_ai_controlled)}
                    className={convDetails.is_ai_controlled ? 'btn-success' : 'btn-warning'}
                    style={{ 
                      padding: '0.25rem 0.75rem', 
                      borderRadius: '12px', 
                      border: 'none', 
                      fontSize: '0.75rem', 
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      background: convDetails.is_ai_controlled ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                      color: convDetails.is_ai_controlled ? 'var(--success)' : '#F59E0B'
                    }}
                  >
                    {convDetails.is_ai_controlled ? <><Bot size={14} /> AI Mode</> : <><User size={14} /> Human Mode</>}
                  </button>
                </div>
              </div>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {convDetails.messages && convDetails.messages.map((msg, idx) => {
                const isIncoming = msg.direction === 'inbound';
                return (
                  <div key={idx} style={{ 
                    alignSelf: isIncoming ? 'flex-start' : 'flex-end',
                    maxWidth: '70%',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.25rem'
                  }}>
                    <div style={{ 
                      background: isIncoming ? 'var(--bg-panel)' : 'var(--accent-primary)',
                      color: isIncoming ? 'var(--text-primary)' : '#fff',
                      padding: '0.75rem 1rem',
                      borderRadius: '16px',
                      border: isIncoming ? '1px solid var(--border-color)' : 'none',
                      borderBottomLeftRadius: isIncoming ? '4px' : '16px',
                      borderBottomRightRadius: !isIncoming ? '4px' : '16px',
                      fontSize: '0.9rem',
                      lineHeight: 1.5,
                      whiteSpace: 'pre-wrap'
                    }}>
                      {msg.content}
                    </div>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', alignSelf: isIncoming ? 'flex-start' : 'flex-end', padding: '0 0.5rem' }}>
                      {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
            
            {/* Input area (disabled for AI mode) */}
            <div style={{ padding: '1rem', borderTop: '1px solid var(--border-color)', background: 'var(--bg-panel)' }}>
              {convDetails.is_ai_controlled ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', color: 'var(--text-secondary)', padding: '0.5rem' }}>
                  <Bot size={16} />
                  <span style={{ fontSize: '0.875rem' }}>AI is managing this conversation. Take over to send manual messages.</span>
                </div>
              ) : (
                <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '0.5rem' }}>
                  <input 
                    type="text" 
                    placeholder="Type a message to send to the customer..." 
                    style={{ flex: 1, background: 'var(--bg-panel-hover)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.75rem 1rem', color: 'var(--text-primary)', outline: 'none' }} 
                    value={messageInput}
                    onChange={(e) => setMessageInput(e.target.value)}
                    disabled={isSending}
                  />
                  <button type="submit" className="btn btn-primary" disabled={!messageInput.trim() || isSending}>
                    {isSending ? 'Sending...' : 'Send'}
                  </button>
                </form>
              )}
            </div>
          </>
        ) : (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            Select a conversation from the left to view history
          </div>
        )}
      </div>
    </div>
  );
};

export default ConversationView;
