import Link from "next/link";

const calendarDays = [
  { day: "Mon", date: 5, muted: true },
  { day: "Tue", date: 6, muted: true },
  { day: "Wed", date: 7, muted: true },
  { day: "Thu", date: 8, muted: false },
  { day: "Fri", date: 9, muted: false },
  { day: "Sat", date: 10, muted: false },
  { day: "Sun", date: 11, muted: false },
];

const itineraryItems = [
  {
    day: 8,
    time: "12:40",
    title: "Arrive in Lisbon",
    detail: "Check in · Baixa",
    tone: "coral",
  },
  {
    day: 9,
    time: "10:00",
    title: "Belém morning",
    detail: "Pasteis de Belém · river walk",
    tone: "yellow",
  },
  {
    day: 10,
    time: "11:30",
    title: "Alfama wander",
    detail: "Fado · sunset at Graça",
    tone: "sage",
  },
  {
    day: 11,
    time: "15:25",
    title: "Fly home",
    detail: "LIS → JFK",
    tone: "ink",
  },
];

export default function ItineraryExperience() {
  return (
    <main className="itinerary-page">
      <header className="itinerary-header">
        <Link className="brand" href="/" aria-label="Go to Plana home">
          <span className="brand__mark" aria-hidden="true">p</span>
          <span>plana</span>
        </Link>
        <p className="itinerary-header__eyebrow">Your next trip</p>
      </header>

      <section className="itinerary-intro" aria-labelledby="itinerary-title">
        <div>
          <p className="itinerary-intro__eyebrow">Lisbon, Portugal</p>
          <h1 id="itinerary-title">A long weekend, unhurried.</h1>
        </div>
        <p className="itinerary-intro__dates">October 8–11, 2026</p>
      </section>

      <section className="calendar" aria-label="Lisbon itinerary calendar">
        <div className="calendar__toolbar">
          <div>
            <p className="calendar__label">Itinerary</p>
            <h2>October 2026</h2>
          </div>
          <span className="calendar__trip-length">4 days in Lisbon</span>
        </div>

        <div className="calendar__weekdays" aria-hidden="true">
          {calendarDays.map(({ day }) => <span key={day}>{day}</span>)}
        </div>
        <div className="calendar__grid">
          {calendarDays.map(({ day, date, muted }) => {
            const entries = itineraryItems.filter((item) => item.day === date);

            return (
              <article
                className={`calendar__day${muted ? " is-muted" : ""}`}
                key={day}
              >
                <div className="calendar__day-header">
                  <span className="calendar__day-name">{day}</span>
                  <time dateTime={`2026-10-${String(date).padStart(2, "0")}`}>
                    {date}
                  </time>
                </div>
                <div className="calendar__items">
                  {entries.map((item) => (
                    <div className={`calendar-item calendar-item--${item.tone}`} key={item.title}>
                      <span>{item.time}</span>
                      <strong>{item.title}</strong>
                      <small>{item.detail}</small>
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <p className="itinerary-note">
        Keep the days light. Plan A is ready in the corner whenever you want to talk through a change.
      </p>
    </main>
  );
}
