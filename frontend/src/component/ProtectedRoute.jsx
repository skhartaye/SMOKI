import { Navigate } from 'react-router-dom'

function ProtectedRoute({ children }) {
  const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true'

  if (!isLoggedIn) {
    // redirect to login page if not logged in
    return <Navigate to="/" replace />
  }

  return children
}

export default ProtectedRoute