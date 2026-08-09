import Link from "next/link";

export default function Home() {
  return (
    <main className="landing-page">
      <header className="landing-header">
        <span className="brand">
          <span className="brand__mark" aria-hidden="true">p</span>
          <span>plana</span>
        </span>
      </header>

      <section className="landing-hero" aria-labelledby="landing-title">
        <p className="landing-hero__eyebrow">Travel planning, simply</p>
        <h1 id="landing-title">Make room for the trip.</h1>
        <p>
          A quiet place to hold the shape of what’s next — and talk it through when you need to.
        </p>
        <Link className="landing-hero__cta" href="/itinerary">
          View your itinerary
          <span aria-hidden="true">→</span>
        </Link>
      </section>
    </main>
  );
}
