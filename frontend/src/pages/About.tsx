import { Link } from 'react-router-dom'

export default function About() {
  return (
    <div style={{ padding: '2rem' }}>
      <h1>About Page</h1>
      <p>This is an example page using React Router v7.</p>
      <div style={{ marginTop: '2rem' }}>
        <Link to="/" style={{ color: '#646cff' }}>
          Go back to Home
        </Link>
      </div>
    </div>
  )
}
