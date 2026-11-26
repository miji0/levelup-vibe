/* eslint-disable @next/next/no-img-element -- The multicolor Figma SVG keeps its intrinsic geometry. */
import type { CSSProperties } from "react";

const assets = {
  brand: ["a55e7.svg", 18, 18],
  brandMobile: ["d95fa.svg", 16, 16],
  home: ["9d27e.svg", 18, 18],
  newspaper: ["db3ea.svg", 18, 18],
  report: ["8df6b.svg", 18, 18],
  settings: ["8debf.svg", 18, 18],
  clock: ["5cc0d.svg", 16, 16],
  timezone: ["710db.svg", 18, 18],
  sun: ["01e4b.svg", 22.75, 22.75],
  moon: ["74f34.svg", 19.9336, 20],
  logout: ["2e8d8.svg", 16, 16],
  menu: ["11412.svg", 16, 16],
  close: ["4847f.svg", 16, 16],
  rss: ["5e92f.svg", 20, 20],
  mail: ["dc5d1.svg", 20, 20],
  mailSmall: ["f9a11.svg", 18, 18],
  plus: ["7deb8.svg", 16, 16],
  empty: ["b6330.svg", 24, 24],
  pending: ["0c7ea.svg", 14, 14],
  newsSmall: ["6ad9e.svg", 18, 18],
  contrast: ["fe90a.svg", 24, 24],
  success: ["5c9fc.svg", 14, 14],
  warning: ["1d8cc.svg", 14, 14],
  refresh: ["1516b.svg", 16, 16],
  unlink: ["7694e.svg", 16, 16],
  send: ["1be26.svg", 16, 16],
  trash: ["cd50f.svg", 16, 16],
  external: ["91c41.svg", 16, 16],
  bookmark: ["4ece9.svg", 16, 16],
  eye: ["01a11.svg", 16, 16],
  search: ["c3ba4.svg", 16, 16],
  copy: ["d70eb.svg", 16, 16],
} as const;
export type IconName = keyof typeof assets;

export function Icon({ name }: { name: IconName }) {
  const [file, width, height] = assets[name];
  return (
    <span
      aria-hidden="true"
      className="design-icon"
      style={
        {
          width,
          height,
          maskImage: `url(/figma/${file})`,
          WebkitMaskImage: `url(/figma/${file})`,
        } as CSSProperties
      }
    />
  );
}
export function GoogleIcon() {
  return (
    <img
      className="google-logo"
      src="/figma/9d9b6.svg"
      alt=""
      aria-hidden="true"
    />
  );
}
export function Brand() {
  return (
    <span className="wordmark">
      <span className="brand-mark">
        <span className="brand-desktop">
          <Icon name="brand" />
        </span>
        <span className="brand-mobile">
          <Icon name="brandMobile" />
        </span>
      </span>
      LevelUp
    </span>
  );
}
