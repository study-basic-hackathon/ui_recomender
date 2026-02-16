import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom';

export default function ErrorPage() {
  const error = useRouteError();

  let errorMessage: string;
  let errorStatus: number | undefined;

  if (isRouteErrorResponse(error)) {
    errorStatus = error.status;
    errorMessage = error.statusText || error.data?.message || 'An error occurred';
  } else if (error instanceof Error) {
    errorMessage = error.message;
  } else {
    errorMessage = 'Unknown error occurred';
  }

  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h1>{errorStatus || 'Oops!'}</h1>
      <p>Sorry, an unexpected error has occurred.</p>
      <p style={{ color: '#888' }}>
        <i>{errorMessage}</i>
      </p>
      <Link to="/" style={{ color: '#646cff', textDecoration: 'underline' }}>
        Go back to home
      </Link>
    </div>
  );
}
