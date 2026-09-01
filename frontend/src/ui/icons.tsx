import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 20, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
    ...props,
  };
}



export function IconGiornata(props: IconProps) {
  return (
    <svg {...base(props)}>
      <rect x="3" y="3.5" width="14" height="13" rx="1" />
      <path d="M3 7.5h14" />
      <path d="M6.5 11h4" />
      <path d="M6.5 13.75h7" />
      <circle cx="14" cy="11" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconRosa(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M7.25 3.5 4 5.75l1.5 3-1 8h11l-1-8 1.5-3-3.25-2.25a2.9 2.9 0 0 1-5.5 0Z" />
    </svg>
  );
}

export function IconMercato(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M4 7h10.5" />
      <path d="m12 4.5 2.5 2.5L12 9.5" />
      <path d="M16 13H5.5" />
      <path d="m8 10.5-2.5 2.5L8 15.5" />
    </svg>
  );
}

export function IconGiocatori(props: IconProps) {
  return (
    <svg {...base(props)}>
      <circle cx="10" cy="6.75" r="3" />
      <path d="M4.5 16.5c.6-3.2 2.8-4.75 5.5-4.75s4.9 1.55 5.5 4.75" />
    </svg>
  );
}

export function IconLega(props: IconProps) {
  return (
    <svg {...base(props)}>
      <path d="M10 3 4.5 4.75v5.1c0 3.3 2.3 5.6 5.5 6.9 3.2-1.3 5.5-3.6 5.5-6.9v-5.1L10 3Z" />
      <path d="M10 3v13.7" />
    </svg>
  );
}



export function IconChevron(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })} className="icon-chevron">
      <path d="m7 4.5 5 5.5-5 5.5" />
    </svg>
  );
}

export function IconPlus(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })}>
      <path d="M10 4v12M4 10h12" />
    </svg>
  );
}

export function IconRefresh(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })}>
      <path d="M16 10a6 6 0 1 1-1.76-4.24" />
      <path d="M16 3.5V6h-2.5" />
    </svg>
  );
}

export function IconX(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })}>
      <path d="m5 5 10 10M15 5 5 15" />
    </svg>
  );
}

export function IconSearch(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })}>
      <circle cx="9" cy="9" r="5" />
      <path d="m12.75 12.75 3.75 3.75" />
    </svg>
  );
}

export function IconPencil(props: IconProps) {
  return (
    <svg {...base({ size: 16, ...props })}>
      <path d="M12.5 3.75 16.25 7.5 7 16.75l-4.25.5.5-4.25 9.25-9.25Z" />
    </svg>
  );
}



export function MarkDot(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <circle cx="10" cy="10" r="5" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function MarkRing(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <circle cx="10" cy="10" r="4.75" />
    </svg>
  );
}

export function MarkHalf(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <circle cx="10" cy="10" r="4.75" />
      <path d="M10 5.25a4.75 4.75 0 0 1 0 9.5Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function MarkCross(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <path d="m6 6 8 8M14 6l-8 8" />
    </svg>
  );
}

export function MarkWarn(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <path d="M10 3.5 17 16H3L10 3.5Z" />
      <path d="M10 8.5v3.5" />
      <circle cx="10" cy="13.9" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function MarkCheck(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <path d="m4.5 10.5 3.5 3.5 7.5-8" />
    </svg>
  );
}

export function MarkAsk(props: IconProps) {
  return (
    <svg {...base({ size: 14, ...props })}>
      <path d="M7.5 7.5a2.5 2.5 0 1 1 3.4 2.33c-.72.28-.9.92-.9 1.67" />
      <circle cx="10" cy="14.4" r="0.8" fill="currentColor" stroke="none" />
    </svg>
  );
}
