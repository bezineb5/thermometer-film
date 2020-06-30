import { Component, ViewChild, ElementRef } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { MatSnackBar } from '@angular/material/snack-bar';
import { Socket } from 'ngx-socket-io';
import Quagga from 'quagga';

interface DXNumber {
  dx_number: string;
}

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  @ViewChild('imageFile', { static: true })
  imageFileInput: ElementRef;

  title = 'thermometer-ui';
  temperatures = [{
    'id': 'air',
    'temperature': 10.0,
  },
  {
    'id': 'water',
    'temperature': 12.44343,
  }];
  development = {
    'duration': 365,
    'film': {
      'brand': "My brand",
      'film_type': "My film",
      'dx_number': "012345",
    },
  };

  constructor(private socket: Socket, private _snackBar: MatSnackBar, private http: HttpClient) {
  }

  ngOnInit() {
    //Called after the constructor, initializing input properties, and the first call to ngOnChanges.
    //Add 'implements OnInit' to the class.

    this.socket.on('connect', () => {
      console.log("Connected");
    });
    this.socket.on('measure', (msg) => {
      this.temperatures = msg['temperatures'];
      this.development = msg['development'];
    });
  }

  formatDuration(duration: number): string {
    const minutes = Math.round(duration / 60);
    const seconds = Math.round(duration % 60);
    return "" + minutes + ":" + String(seconds).padStart(2, '0');
  }

  mapIcon(temperatureId: string): string {
    switch (temperatureId) {
      case "air":
        return "house";
      case "water":
        return "pool";
      default:
        return "";
    }
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

      Quagga.decodeSingle(config, function (result) {
        if (result && 'codeResult' in result) {
          console.log("result", result.codeResult.code);
          return self.http.post<DXNumber>("/dx", { "dx_number": result.codeResult.code })
            .pipe(
              catchError((error: HttpErrorResponse) => {
                if (error.error instanceof ErrorEvent) {
                  console.error('An error occurred:', error.error.message);
                } else {
                  self.showSnack('Unknown DX barcode');
                  return throwError(
                    'Something bad happened; please try again later.');
                }
              })
            ).subscribe(dx => self.showSnack('DX code: ' + dx.dx_number)
            );
        } else {
          self.showSnack('Unrecognized DX barcode');
        }
      });
    }
  }

  startScanDXBarcode() {
    this.imageFileInput.nativeElement.click();
  }

  showSnack(text: string) {
    this._snackBar.open(text, undefined, {
      duration: 1000
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