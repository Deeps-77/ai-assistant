"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

const NAV = [
  { href: "/", icon: "⬡", label: "Dashboard" },
  { href: "/chat", icon: "💬", label: "Chat" },
  { href: "/projects", icon: "📁", label: "Projects" },
  { href: "/analytics", icon: "📊", label: "Analytics" },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>
        <span className={styles.logoIcon}>⬡</span>
        <span className={styles.logoText}>DeliveryAI</span>
      </div>
      <nav className={styles.nav}>
        <p className={styles.navSection}>Menu</p>
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className={`${styles.navItem} ${path === n.href ? styles.active : ""}`}
          >
            <span className={styles.navIcon}>{n.icon}</span>
            <span>{n.label}</span>
          </Link>
        ))}
      </nav>
      <div className={styles.footer}>
        <div className={styles.statusDot} />
        <span>Backend online</span>
      </div>
    </aside>
  );
}
