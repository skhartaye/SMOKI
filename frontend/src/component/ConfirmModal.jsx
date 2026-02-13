import { AlertCircle } from 'lucide-react';
import '../styles/ConfirmModal.css';

export default function ConfirmModal({ 
  isOpen, 
  title = 'Confirm Action', 
  message = 'Are you sure?', 
  onConfirm, 
  onCancel,
  confirmText = 'Delete',
  cancelText = 'Cancel',
  isDangerous = false
}) {
  if (!isOpen) return null;

  return (
    <div className="confirm-modal-overlay" onClick={onCancel}>
      <div className="confirm-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-modal-icon">
          <AlertCircle size={32} />
        </div>
        
        <h2 className="confirm-modal-title">{title}</h2>
        <p className="confirm-modal-message">{message}</p>
        
        <div className="confirm-modal-actions">
          <button 
            className="confirm-modal-cancel"
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button 
            className={`confirm-modal-confirm ${isDangerous ? 'dangerous' : ''}`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
