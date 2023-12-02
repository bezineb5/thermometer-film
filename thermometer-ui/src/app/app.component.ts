import { Component, ViewChild, ElementRef, NgZone } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MatSnackBar } from '@angular/material/snack-bar';
import Quagga from 'quagga';
import { OnInit } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { NgFor, DecimalPipe } from '@angular/common';
import { MatListModule } from '@angular/material/list';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { environment } from '../environments/environment';
import { DurationPipe } from './duration.pipe';

interface DXNumber {
  dx_number: string;
}

interface ScanResult {
  codeResult: {
    code: DXNumber;
  };
};

interface Temperature {
  id: string;
  temperature: number;
}

interface Development {
  duration: number;
  film: {
    brand: string;
    film_type: string;
    dx_number: string;
  };
  error?: string;
}

interface Message {
  temperatures?: Temperature[];
  development?: Development;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: true,
  imports: [MatCardModule, MatButtonModule, MatListModule, NgFor, MatIconModule, DecimalPipe, DurationPipe]
})
export class AppComponent implements OnInit {
  readonly notificationDurationMs = 1000;

  @ViewChild('imageFile', { static: true })
  imageFileInput: ElementRef;

  title = 'thermometer-ui';
  temperatures: Temperature[] = [{
    'id': 'air',
    'temperature': 10.0,
  },
  {
    'id': 'water',
    'temperature': 12.44343,
  }];
  development: Development = {
    'duration': 365,
    'film': {
      'brand': "My brand",
      'film_type': "My film",
      'dx_number': "012345",
    },
    'error': undefined,
  };
  isSocketOpen: boolean = false;

  constructor(private _snackBar: MatSnackBar, private http: HttpClient, private ngZone: NgZone) {
  }

  ngOnInit() {
    //Called after the constructor, initializing input properties, and the first call to ngOnChanges.
    this.initServerSentEvents();
  }

  private initServerSentEvents(): void {
    const sseUrl = this.getLiveStatusUrl("/stream");
    console.log("SSE url: ", sseUrl);
    const evtSource = new EventSource(sseUrl);

    evtSource.onopen = (event) => {
      this.ngZone.run(() => {
        console.log("SSE opened: ", event);
        this.isSocketOpen = true;
      });
    };
    evtSource.onerror = (_event) => {
      this.ngZone.run(() => {
        if (this.isSocketOpen) {
          this.showMessage("Connection lost");
        }
        this.isSocketOpen = false;
      });
    };
    evtSource.onmessage = (event) => {
      // We need to run the callback in the Angular zone because otherwise
      // the UI won't be updated.
      // See: https://angular.io/guide/zone
      this.ngZone.run(() => {
        const message: Message = JSON.parse(event.data);
        if (!environment.production) {
          console.log("SSE message: ", message);
        }
        this.onMessage(message);
      });
    };
  }

  private getLiveStatusUrl(path: string): string {
    const hostname = environment.hostname || "";
    return hostname + path;
  }

  private onMessage(message: Message): void {
    const newTemperatures = message['temperatures'];
    if (!newTemperatures) {
      return;
    }
    // Order by id to have consistent display
    newTemperatures.sort((a, b) => a['id'].localeCompare(b['id']));
    this.temperatures = newTemperatures;

    const newDevelopment = message['development'];
    if (!newDevelopment) {
      return;
    }
    this.development = newDevelopment;
  }

  onFileScan(e) {
    let self = this;

    if (e.target.files && e.target.files.length) {
      const src = URL.createObjectURL(e.target.files[0]);
      const config = {
        src: src,
        locate: true, // try to locate the barcode in the image
        decoder: {
          // DX barcodes are IFT (Interleaved 2 of 5 barcodes): https://en.wikipedia.org/wiki/DX_encoding
          readers: ["i2of5_reader"]
        }
      };

      Quagga.decodeSingle(config, function (result: ScanResult) {
        if (result && 'codeResult' in result) {
          console.log("result", result.codeResult.code);
          self.setDxNumber(result.codeResult.code);
        } else {
          self.showMessage('Unrecognized DX barcode');
        }
      });
    }
  }

  private setDxNumber(dxCode: DXNumber) {
    return this.http.post<DXNumber>("/dx", { "dx_number": dxCode })
      .pipe(
        catchError((error: HttpErrorResponse) => {
          if (error.error instanceof ErrorEvent) {
            console.error('An error occurred:', error.error.message);
          } else {
            this.showMessage('Unknown DX barcode');
            return throwError(() => new Error('Something bad happened; please try again later.'));
          }
        })
      ).subscribe(
        (dx: DXNumber) => this.showMessage('DX code: ' + dx.dx_number)
      );
  }

  startScanDXBarcode() {
    this.imageFileInput.nativeElement.click();
  }

  private showMessage(text: string) {
    this._snackBar.open(text, undefined, {
      duration: this.notificationDurationMs,
    });
  }
}

/**
 * String.padStart()
 * version 1.0.1
 * Feature	        Chrome  Firefox Internet Explorer   Opera	Safari	Edge
 * Basic support	57   	51      (No)	            44   	10      15
 * -------------------------------------------------------------------------------
 */
if (!String.prototype.padStart) {
  String.prototype.padStart = function padStart(targetLength, padString) {
    targetLength = targetLength >> 0; //floor if number or convert non-number to 0;
    padString = String(typeof padString !== 'undefined' ? padString : ' ');
    if (this.length > targetLength) {
      return String(this);
    } else {
      targetLength = targetLength - this.length;
      if (targetLength > padString.length) {
        padString += padString.repeat(targetLength / padString.length); //append to original to ensure we are longer than needed
      }
      return padString.slice(0, targetLength) + String(this);
    }
  };
}