import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import PageHeader from "../components/ui/PageHeader";
import Button from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import Banner from "../components/ui/Banner";

export default function PendingAccessPage() {
  const { user, logout } = useAuth();

  return (
    <>
      <PageHeader
        eyebrow="Access"
        title="Waiting for role assignment"
        subtitle="Your account is signed in but does not have a business role yet."
      />
      <Card className="max-w-xl">
        <CardBody className="space-y-4">
          <Banner tone="info">
            Signed in as <strong>{user?.email}</strong>. Ask the owner to assign you a role on the Users page.
          </Banner>
          <p className="text-sm text-ink-muted">
            Until a role is assigned, inventory, bills, and other business features stay locked. You can sign out and try
            another account, or wait for the owner to grant access.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" onClick={() => logout()}>
              Sign out
            </Button>
            <Link to="/home">
              <Button variant="ghost">About</Button>
            </Link>
          </div>
        </CardBody>
      </Card>
    </>
  );
}
