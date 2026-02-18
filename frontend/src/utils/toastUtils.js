// Helper function to show toast
export const showToast = (type, message, duration = 3000) => {
  window.dispatchEvent(new CustomEvent('showToast', {
    detail: { type, message, duration }
  }));
};
