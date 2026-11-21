export function clamp(n:number,min?:number,max?:number):number;
export function cubic(a:{x:number;y:number},b:{x:number;y:number},c:{x:number;y:number},d:{x:number;y:number},t:number):{x:number;y:number};
export function evaporation(t:number,lane?:number):{x:number;y:number};
export function runoff(t:number):{x:number;y:number};
export function phaseAt<T extends {start_seconds:number;end_seconds:number}>(scenes:T[],seconds:number):T;
export function localAsset(value:unknown):boolean;
